"""FastAPI entrypoint for QuerySense backend."""

import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models import AnalyzeRequest
from .sql_parser import parse_sql
from .db import explain_query, run_preview, fetch_table_columns
from .plan_summary import summarize_plan
from .rules import run_rules, build_index_recommendations, score_findings
from .llm import generate_explanation
from .rewrite import rewrite_query
from .memory import append_example, find_similar
from .training_store import (
    ensure_training_table,
    export_training_data,
    get_training_stats,
    get_training_trends,
    list_training_examples,
    store_training_example,
    update_feedback,
)
from .ollama_logs import get_logs
from .settings import LLM_ONLY_REWRITE, MEMORY_REWRITE_ENABLED

app = FastAPI(title="SQL Analyst MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.on_event("startup")
def startup() -> None:
    """Create the training table if it is missing."""
    try:
        ensure_training_table()
    except Exception as exc:
        logging.warning("Training table setup failed: %s", exc)


@app.get("/api/health")
def health() -> dict:
    """Simple health check used by the UI."""
    return {"status": "ok"}


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest) -> dict:
    """Analyze a SQL query and return explainable optimization advice."""
    warnings = []
    original_sql = request.sql

    try:
        normalized_sql, parsed_sql = parse_sql(original_sql)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    preview = None
    if request.run_preview:
        try:
            preview = run_preview(normalized_sql)
        except Exception as exc:
            warnings.append(f"Preview failed: {exc}")

    plan = None
    try:
        plan = explain_query(normalized_sql, analyze=request.run_analyze)
    except Exception as exc:
        warnings.append(f"Explain failed: {exc}")

    columns_by_table = {}
    try:
        columns_by_table = fetch_table_columns(parsed_sql.get("tables", []))
    except Exception as exc:
        warnings.append(f"Schema lookup failed: {exc}")

    plan_summary = summarize_plan(plan) if plan else None
    rule_findings = run_rules(parsed_sql, plan)
    index_recommendations = build_index_recommendations(parsed_sql, columns_by_table)
    optimization_score = score_findings(rule_findings)
    why_slow = [
        {
            "title": finding.get("title"),
            "rationale": finding.get("rationale"),
            "severity": finding.get("severity"),
        }
        for finding in rule_findings
        if int(finding.get("severity", 1)) >= 2
    ]

    memory_examples = find_similar(original_sql, limit=3)
    llm_payload = {
        "original_sql": original_sql,
        "normalized_sql": normalized_sql,
        "parsed_sql": parsed_sql,
        "plan_summary": plan_summary,
        "rule_findings": rule_findings,
        "columns_by_table": columns_by_table,
        "memory_examples": memory_examples,
        "index_recommendations": index_recommendations,
        "optimization_score": optimization_score,
    }
    llm_output = generate_explanation(llm_payload, mode=request.analysis_mode)

    if not LLM_ONLY_REWRITE:
        rule_rewrite, rewrite_notes = rewrite_query(
            original_sql, parsed_sql, columns_by_table
        )
        if rule_rewrite:
            if not llm_output:
                llm_output = {
                    "explanation": "",
                    "suggested_sql": None,
                    "recommendation_rationale": None,
                    "rewrite_source": None,
                }
            if not llm_output.get("suggested_sql"):
                llm_output["suggested_sql"] = rule_rewrite
                llm_output["rewrite_source"] = "rules"
                if not llm_output.get("explanation"):
                    llm_output["explanation"] = "Rule-based rewrite generated from schema metadata."
                if rewrite_notes:
                    llm_output["recommendation_rationale"] = " ".join(rewrite_notes)

    if (
        MEMORY_REWRITE_ENABLED
        and llm_output
        and not llm_output.get("suggested_sql")
        and memory_examples
    ):
        best = memory_examples[0]
        if best.get("similarity", 0) >= 0.4 and best.get("suggested_sql"):
            llm_output["suggested_sql"] = best["suggested_sql"]
            llm_output["rewrite_source"] = f"memory:{best.get('source', 'memory')}"
            llm_output["recommendation_rationale"] = (
                f"Reused a prior rewrite with similarity {best.get('similarity')}."
            )

    if llm_output and llm_output.get("suggested_sql"):
        if llm_output["suggested_sql"].strip() != original_sql.strip():
            append_example(
                original_sql,
                llm_output["suggested_sql"],
                note=llm_output.get("recommendation_rationale", "") or "",
            )

    try:
        store_training_example(
            {
                "model_used": (llm_output or {}).get("model_used"),
                "original_sql": original_sql,
                "normalized_sql": normalized_sql,
                "parsed_sql": parsed_sql,
                "plan_summary": plan_summary,
                "rule_findings": rule_findings,
                "index_recommendations": index_recommendations,
                "optimization_score": optimization_score,
                "llm_payload": llm_payload,
                "llm_output": llm_output,
                "run_analyze": request.run_analyze,
                "run_preview": request.run_preview,
                "warnings": warnings,
            }
        )
    except Exception as exc:
        warnings.append(f"Training store failed: {exc}")

    return {
        "original_sql": original_sql,
        "parsed_sql": parsed_sql,
        "plan_summary": plan_summary,
        "rule_findings": rule_findings,
        "llm": llm_output,
        "insights": {
            "why_slow": why_slow,
            "index_recommendations": index_recommendations,
            "optimization_score": optimization_score,
        },
        "preview": preview,
        "raw_plan": plan,
        "warnings": warnings,
    }


@app.get("/api/ollama/logs")
def ollama_logs(limit: int = 120) -> dict:
    """Return recent LLM logs so the UI can show live activity."""
    return {"logs": get_logs(limit)}


@app.get("/api/training/stats")
def training_stats(
    label: str | None = None,
    model: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Return counts and averages for the evaluation dashboard."""
    return get_training_stats(
        label=label,
        model=model,
        date_from=date_from,
        date_to=date_to,
    )


@app.get("/api/training/list")
def training_list(
    limit: int = 30,
    offset: int = 0,
    label: str | None = None,
    model: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    unlabeled_first: bool = False,
) -> dict:
    """Return recent training rows for the tagging UI."""
    return {
        "rows": list_training_examples(
            limit=limit,
            offset=offset,
            label=label,
            model=model,
            date_from=date_from,
            date_to=date_to,
            unlabeled_first=unlabeled_first,
        )
    }


@app.post("/api/training/label")
def training_label(payload: dict) -> dict:
    """Save a Good/Bad label for a training row."""
    example_id = int(payload.get("id"))
    label = str(payload.get("label", "")).strip()
    notes = payload.get("notes")
    if label not in {"good", "bad", "needs_review"}:
        raise HTTPException(status_code=400, detail="Label must be good, bad, or needs_review.")
    update_feedback(example_id, label, notes)
    return {"status": "ok"}


@app.get("/api/training/export")
def training_export(
    format: str = "jsonl",
    limit: int = 1000,
    label: str | None = None,
    model: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Export training rows for offline fine-tuning."""
    rows = export_training_data(
        limit=limit,
        label=label,
        model=model,
        date_from=date_from,
        date_to=date_to,
    )
    if format not in {"jsonl", "csv"}:
        raise HTTPException(status_code=400, detail="Format must be jsonl or csv.")
    return {"format": format, "rows": rows}


@app.get("/api/training/trends")
def training_trends(
    days: int = 30,
    label: str | None = None,
    model: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Return average score trends for the UI chart."""
    return {
        "points": get_training_trends(
            days=days,
            label=label,
            model=model,
            date_from=date_from,
            date_to=date_to,
        )
    }
