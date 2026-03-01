"""Talk to the local LLM and get back explanations and rewrites."""

from typing import Any, Dict
import hashlib
import json
import threading
import time

import httpx

from .settings import (
    LLM_COOLDOWN_SECONDS,
    LLM_CACHE_TTL_SECONDS,
    LLM_ENABLED,
    LLM_KEEP_ALIVE,
    LLM_LIVE_ENABLED,
    LLM_LIVE_MAX_SQL_CHARS,
    LLM_LOCK_WAIT_SECONDS,
    LLM_MAX_FINDINGS_LIVE,
    LLM_MAX_FINDINGS_MANUAL,
    LLM_MAX_INDEX_LIVE,
    LLM_MAX_INDEX_MANUAL,
    LLM_MAX_MEMORY_LIVE,
    LLM_MAX_MEMORY_MANUAL,
    LLM_MAX_PREDICT_LIVE,
    LLM_MAX_PREDICT_MANUAL,
    LLM_NUM_CTX_LIVE,
    LLM_NUM_CTX_MANUAL,
    LLM_STREAM,
    LLM_SKIP_IF_BUSY_LIVE,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_LIVE,
    LLM_TIMEOUT_MANUAL,
    LLM_TOP_P,
    OLLAMA_MODEL,
    OLLAMA_MODEL_FALLBACKS,
    OLLAMA_MODEL_LIVE,
    OLLAMA_MODEL_MANUAL,
    OLLAMA_URL,
)
from .ollama_logs import log_event

_LIVE_COOLDOWN_UNTIL = 0.0
_LIVE_COOLDOWN_REASON = ""
_LLM_LOCK = threading.Lock()
_LLM_CACHE: Dict[str, tuple[float, Dict[str, Any]]] = {}


def _extract_json(text: str) -> Dict[str, Any] | None:
    """Pull the first JSON object out of a text blob."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start : end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        return None


def _list_models() -> list[str]:
    """Ask Ollama what models are installed."""
    response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    response.raise_for_status()
    payload = response.json() or {}
    models = payload.get("models", [])
    names = [item.get("name") for item in models if item.get("name")]
    return names


def _unique(values: list[str]) -> list[str]:
    """Return unique values while keeping the original order."""
    output = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _preferred_models(mode: str) -> list[str]:
    """Choose model priority by mode so live requests stay lightweight."""
    primary = OLLAMA_MODEL_LIVE if mode == "live" else OLLAMA_MODEL_MANUAL
    return _unique([primary, OLLAMA_MODEL, *OLLAMA_MODEL_FALLBACKS])


def _resolve_models(mode: str) -> tuple[list[str], list[str]]:
    """Resolve installed models with deterministic fallback order."""
    preferred = _preferred_models(mode)
    try:
        installed = _list_models()
    except Exception as exc:
        log_event("warn", "Unable to list models", {"detail": str(exc)[:200]})
        return preferred, []

    installed_preferred = [name for name in preferred if name in installed]
    if installed_preferred:
        return installed_preferred, installed
    if preferred:
        # Keep model choice deterministic; do not jump to unrelated installed models.
        return preferred, installed
    if installed:
        return installed, installed
    return preferred, installed


def _compact_parsed_sql(parsed_sql: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only the SQL details that influence rewrite and explanation quality."""
    return {
        "tables_ordered": parsed_sql.get("tables_ordered", []),
        "table_aliases": parsed_sql.get("table_aliases", []),
        "select_columns": parsed_sql.get("select_columns", []),
        "has_select_star": parsed_sql.get("has_select_star", False),
        "has_where": parsed_sql.get("has_where", False),
        "where": parsed_sql.get("where"),
        "functions_in_where": parsed_sql.get("functions_in_where", []),
        "joins": parsed_sql.get("joins", []),
        "join_conditions": parsed_sql.get("join_conditions", []),
        "order_by": parsed_sql.get("order_by", []),
        "group_by": parsed_sql.get("group_by", []),
        "limit": parsed_sql.get("limit"),
        "has_distinct": parsed_sql.get("has_distinct", False),
        "has_cte": parsed_sql.get("has_cte", False),
        "has_subquery": parsed_sql.get("has_subquery", False),
        "in_subqueries": parsed_sql.get("in_subqueries", []),
        "subquery_count": parsed_sql.get("subquery_count", 0),
    }


def _trim_payload(payload: Dict[str, Any], mode: str) -> Dict[str, Any]:
    """Keep the payload small so the LLM responds faster on CPU-only machines."""
    data = dict(payload)
    if mode == "live":
        max_findings = LLM_MAX_FINDINGS_LIVE
        max_index = LLM_MAX_INDEX_LIVE
        max_memory = LLM_MAX_MEMORY_LIVE
    else:
        max_findings = LLM_MAX_FINDINGS_MANUAL
        max_index = LLM_MAX_INDEX_MANUAL
        max_memory = LLM_MAX_MEMORY_MANUAL

    if isinstance(data.get("rule_findings"), list):
        data["rule_findings"] = data["rule_findings"][:max_findings]
    if isinstance(data.get("index_recommendations"), list):
        data["index_recommendations"] = data["index_recommendations"][:max_index]
    if isinstance(data.get("memory_examples"), list):
        data["memory_examples"] = data["memory_examples"][:max_memory]
    if isinstance(data.get("parsed_sql"), dict):
        data["parsed_sql"] = _compact_parsed_sql(data["parsed_sql"])

    return data


def _is_retryable_status(status_code: int) -> bool:
    """Mark transient server overload statuses as retryable."""
    return status_code in {408, 429, 500, 502, 503, 504}


def _is_resource_error(detail: str) -> bool:
    """Detect memory and runtime pressure errors from Ollama."""
    text = detail.lower()
    patterns = (
        "requires more system memory",
        "out of memory",
        "model is too large",
        "timed out",
        "timeout",
        "context deadline exceeded",
        "connection reset",
    )
    return any(pattern in text for pattern in patterns)


def _set_live_cooldown(reason: str) -> None:
    """Pause live LLM calls for a short window after repeated pressure errors."""
    global _LIVE_COOLDOWN_UNTIL, _LIVE_COOLDOWN_REASON
    _LIVE_COOLDOWN_UNTIL = time.time() + max(0, LLM_COOLDOWN_SECONDS)
    _LIVE_COOLDOWN_REASON = reason


def _live_cooldown() -> tuple[bool, int, str]:
    """Return live cooldown status and remaining seconds."""
    remaining = int(max(0, _LIVE_COOLDOWN_UNTIL - time.time()))
    return remaining > 0, remaining, _LIVE_COOLDOWN_REASON


def _build_prompt(payload: Dict[str, Any]) -> str:
    """Build a strict grounding prompt that keeps output JSON-only."""
    return (
        "You are a SQL performance assistant. Use ONLY the input facts. "
        "Do not invent schema, indexes, or planner behavior. "
        "Try one safe equivalent rewrite when possible. "
        "Prefer replacing IN subqueries with JOIN/EXISTS only when semantics are preserved. "
        "Use original_sql style and casing where practical. "
        "If rewrite safety is uncertain, leave suggested_sql empty and explain. "
        "Return ONLY JSON with keys: explanation, suggested_sql, recommendation_rationale. "
        "Keep explanation concise: max 6 bullet points total across sections. "
        "In explanation use sections: WHY THIS QUERY IS SLOW, OPTIMIZED QUERY, INDEX RECOMMENDATIONS.\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, indent=2)}\n"
    )


def _cache_key(mode: str, payload: Dict[str, Any]) -> str:
    """Build a stable cache key so repeated prompts reuse prior results."""
    material = {
        "mode": mode,
        "payload": payload,
    }
    encoded = json.dumps(material, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()


def _cache_get(key: str) -> Dict[str, Any] | None:
    """Return cached LLM output when the entry is still fresh."""
    if LLM_CACHE_TTL_SECONDS <= 0:
        return None
    entry = _LLM_CACHE.get(key)
    if not entry:
        return None
    created_at, value = entry
    if time.time() - created_at > LLM_CACHE_TTL_SECONDS:
        _LLM_CACHE.pop(key, None)
        return None
    return dict(value)


def _cache_set(key: str, value: Dict[str, Any]) -> None:
    """Save successful LLM output for a short window."""
    if LLM_CACHE_TTL_SECONDS <= 0:
        return
    _LLM_CACHE[key] = (time.time(), dict(value))


def _generate_text(
    model_name: str,
    prompt: str,
    timeout_seconds: int,
    num_predict: int,
    num_ctx: int,
) -> str:
    """Call Ollama and return the full text response."""
    request_body = {
        "model": model_name,
        "prompt": prompt,
        "stream": LLM_STREAM,
        "keep_alive": LLM_KEEP_ALIVE,
        "options": {
            "temperature": LLM_TEMPERATURE,
            "top_p": LLM_TOP_P,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
        },
    }
    if LLM_STREAM:
        text_parts = []
        with httpx.stream(
            "POST",
            f"{OLLAMA_URL}/api/generate",
            json=request_body,
            timeout=timeout_seconds,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    # Ignore broken chunks and continue reading stream.
                    continue
                chunk = event.get("response")
                if chunk:
                    text_parts.append(chunk)
                if event.get("done") is True:
                    break
        return "".join(text_parts)

    response = httpx.post(
        f"{OLLAMA_URL}/api/generate",
        json=request_body,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return response.json().get("response", "")


def generate_explanation(payload: Dict[str, Any], mode: str = "manual") -> Dict[str, Any] | None:
    """Send facts to the LLM and get an explanation plus an optional safe rewrite."""
    if not LLM_ENABLED:
        log_event("info", "LLM disabled; skipping generation")
        return None

    mode = "live" if mode == "live" else "manual"
    if mode == "live" and not LLM_LIVE_ENABLED:
        log_event("info", "Live LLM disabled by configuration")
        return None

    original_sql = str(payload.get("original_sql", ""))
    if mode == "live" and len(original_sql) > LLM_LIVE_MAX_SQL_CHARS:
        log_event(
            "info",
            "Live LLM skipped for long query",
            {"sql_chars": len(original_sql), "max_chars": LLM_LIVE_MAX_SQL_CHARS},
        )
        return {
            "explanation": "",
            "error": (
                f"Live LLM skipped for long query ({len(original_sql)} chars). "
                "Use Run Manual Analysis for full rewrite."
            ),
            "model_used": None,
        }

    if mode == "live":
        in_cooldown, remaining, reason = _live_cooldown()
        if in_cooldown:
            return {
                "explanation": "",
                "error": f"Live LLM cooling down for {remaining}s: {reason}",
                "model_used": None,
            }

    payload = _trim_payload(payload, mode)
    cache_key = _cache_key(mode, payload)
    cached = _cache_get(cache_key)
    if cached:
        log_event("info", "LLM cache hit", {"mode": mode})
        return cached

    prompt = _build_prompt(payload)
    candidates, installed = _resolve_models(mode)
    if not candidates:
        return {
            "explanation": "",
            "error": "No local Ollama models found. Pull one with `ollama pull <model>`.",
            "model_used": None,
        }

    timeout_seconds = LLM_TIMEOUT_LIVE if mode == "live" else LLM_TIMEOUT_MANUAL
    num_predict = LLM_MAX_PREDICT_LIVE if mode == "live" else LLM_MAX_PREDICT_MANUAL
    num_ctx = LLM_NUM_CTX_LIVE if mode == "live" else LLM_NUM_CTX_MANUAL
    last_error = "LLM request failed."

    if mode == "live" and LLM_SKIP_IF_BUSY_LIVE:
        acquired = _LLM_LOCK.acquire(blocking=False)
        if not acquired:
            return {
                "explanation": "",
                "error": "Live LLM skipped because the model is busy.",
                "model_used": None,
            }
    else:
        acquired = _LLM_LOCK.acquire(timeout=max(0, LLM_LOCK_WAIT_SECONDS))
        if not acquired:
            return {
                "explanation": "",
                "error": "LLM is busy. Retry in a few seconds.",
                "model_used": None,
            }

    log_event(
        "info",
        "LLM request candidates",
        {
            "mode": mode,
            "candidates": candidates,
            "installed_models": installed,
            "prompt_chars": len(prompt),
        },
    )

    try:
        for index, model_name in enumerate(candidates):
            try:
                started = time.perf_counter()
                text = _generate_text(
                    model_name=model_name,
                    prompt=prompt,
                    timeout_seconds=timeout_seconds,
                    num_predict=num_predict,
                    num_ctx=num_ctx,
                )
                elapsed = round((time.perf_counter() - started) * 1000, 2)
                log_event(
                    "info",
                    "LLM response received",
                    {
                        "model": model_name,
                        "latency_ms": elapsed,
                        "response_preview": text[:260],
                    },
                )

                data = _extract_json(text)
                if not data:
                    result = {
                        "explanation": text.strip(),
                        "error": "LLM did not return JSON.",
                        "model_used": model_name,
                    }
                    log_event("warn", "LLM response missing JSON", {"response_preview": text[:260]})
                    return result

                result = {
                    "explanation": str(data.get("explanation", "")).strip(),
                    "suggested_sql": str(data.get("suggested_sql", "")).strip() or None,
                    "recommendation_rationale": str(data.get("recommendation_rationale", "")).strip()
                    or None,
                    "rewrite_source": "llm",
                    "model_used": model_name,
                }
                _cache_set(cache_key, result)
                return result
            except httpx.TimeoutException:
                last_error = f"LLM timed out after {timeout_seconds}s on model `{model_name}`."
                log_event("warn", "LLM timeout", {"model": model_name, "timeout": timeout_seconds})
                if index < len(candidates) - 1:
                    continue
                if mode == "live":
                    _set_live_cooldown(last_error)
            except httpx.HTTPStatusError as exc:
                detail = ""
                try:
                    detail = exc.response.json().get("error", "")
                except Exception:
                    detail = exc.response.text
                detail = detail.strip()
                last_error = f"LLM HTTP {exc.response.status_code}: {detail}".strip()
                retryable = _is_retryable_status(exc.response.status_code) or _is_resource_error(detail)
                log_event(
                    "error",
                    "LLM HTTP error",
                    {
                        "model": model_name,
                        "status": exc.response.status_code,
                        "detail": detail[:260],
                        "retryable": retryable,
                    },
                )
                if retryable and index < len(candidates) - 1:
                    continue
                if mode == "live" and _is_resource_error(detail):
                    _set_live_cooldown(detail[:200] or "resource pressure")
            except Exception as exc:
                last_error = str(exc)
                log_event("error", "LLM unexpected error", {"model": model_name, "detail": last_error[:260]})
                if index < len(candidates) - 1:
                    continue
                if mode == "live":
                    _set_live_cooldown(last_error[:200] or "unexpected error")
    finally:
        _LLM_LOCK.release()

    return {"explanation": "", "error": last_error, "model_used": None}
