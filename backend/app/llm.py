"""Talk to the local LLM and get back explanations and rewrites."""

from typing import Any, Dict
import json
import httpx
import time

from .settings import (
    LLM_ENABLED,
    LLM_MAX_FINDINGS_LIVE,
    LLM_MAX_FINDINGS_MANUAL,
    LLM_MAX_INDEX_LIVE,
    LLM_MAX_INDEX_MANUAL,
    LLM_MAX_MEMORY_LIVE,
    LLM_MAX_MEMORY_MANUAL,
    LLM_MAX_PREDICT_LIVE,
    LLM_MAX_PREDICT_MANUAL,
    LLM_TIMEOUT_LIVE,
    LLM_TIMEOUT_MANUAL,
    OLLAMA_MODEL,
    OLLAMA_URL,
)
from .ollama_logs import log_event


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


def _resolve_model() -> tuple[str | None, list[str]]:
    """Pick the best available model, falling back if needed."""
    try:
        models = _list_models()
    except Exception as exc:
        log_event("warn", "Unable to list models", {"detail": str(exc)[:200]})
        return OLLAMA_MODEL, []

    if OLLAMA_MODEL in models:
        return OLLAMA_MODEL, models
    if models:
        return models[0], models
    return None, models


def _trim_payload(payload: Dict[str, Any], mode: str) -> Dict[str, Any]:
    """Keep the payload small so the LLM responds faster."""
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
    return data


def generate_explanation(payload: Dict[str, Any], mode: str = "manual") -> Dict[str, Any] | None:
    """Send facts to the LLM and get an explanation + optional rewrite."""
    if not LLM_ENABLED:
        log_event("info", "LLM disabled; skipping generation")
        return None

    mode = "live" if mode == "live" else "manual"
    payload = _trim_payload(payload, mode)

    model_name, available_models = _resolve_model()
    if not model_name:
        return {
            "explanation": "",
            "error": "No local Ollama models found. Pull one with `ollama pull <model>`.",
            "model_used": None,
        }
    if model_name != OLLAMA_MODEL:
        log_event(
            "warn",
            "Fallback to available model",
            {
                "requested": OLLAMA_MODEL,
                "using": model_name,
                "available": available_models,
            },
        )

    prompt = (
        "You are a SQL performance assistant. Use ONLY the facts in the input. "
        "Do not invent indexes, table stats, or planner behavior. "
        "If a recommendation is not supported by the input, say it is unknown. "
        "Try to produce a safer, equivalent SQL rewrite when possible, based only on the input. "
        "Prefer rewriting IN subqueries into JOINs or EXISTS when safe. "
        "Use original_sql as the base for formatting and casing. "
        "If you cannot safely suggest a rewrite, leave suggested_sql empty and explain why. "
        "In the explanation, use sections: "
        "'WHY THIS QUERY IS SLOW', 'OPTIMIZED QUERY', and 'INDEX RECOMMENDATIONS' when relevant. "
        "Return JSON with keys: explanation, suggested_sql, recommendation_rationale.\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, indent=2)}\n"
    )

    try:
        log_event(
            "info",
            "LLM request started",
            {
                "model": model_name,
                "prompt_chars": len(prompt),
            },
        )
        started = time.perf_counter()
        response = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": LLM_MAX_PREDICT_LIVE if mode == "live" else LLM_MAX_PREDICT_MANUAL,
                },
            },
            timeout=LLM_TIMEOUT_LIVE if mode == "live" else LLM_TIMEOUT_MANUAL,
        )
        response.raise_for_status()
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        text = response.json().get("response", "")
        log_event(
            "info",
            "LLM response received",
            {
                "status": response.status_code,
                "latency_ms": elapsed,
                "response_preview": text[:400],
            },
        )
        data = _extract_json(text)
        if not data:
            log_event("warn", "LLM response missing JSON", {"response_preview": text[:400]})
            return {"explanation": text.strip(), "error": "LLM did not return JSON."}

        return {
            "explanation": str(data.get("explanation", "")).strip(),
            "suggested_sql": str(data.get("suggested_sql", "")).strip() or None,
            "recommendation_rationale": str(data.get("recommendation_rationale", "")).strip()
            or None,
            "rewrite_source": "llm",
            "model_used": model_name,
        }
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            detail = exc.response.json().get("error", "")
        except Exception:
            detail = exc.response.text
        log_event(
            "error",
            "LLM HTTP error",
            {
                "status": exc.response.status_code,
                "detail": detail[:400],
            },
        )
        return {
            "explanation": "",
            "error": f"LLM HTTP {exc.response.status_code}: {detail}".strip(),
        }
    except Exception as exc:
        log_event("error", "LLM unexpected error", {"detail": str(exc)[:400]})
        return {"explanation": "", "error": str(exc)}
