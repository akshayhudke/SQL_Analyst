"""Save analysis data so we can train and improve the LLM later."""

from __future__ import annotations

import json
from typing import Any, Dict

import psycopg
from psycopg.types.json import Json

from .settings import DATABASE_URL, TRAINING_STORE_ENABLED


def ensure_training_table() -> None:
    """Make the training table if it is missing."""
    if not TRAINING_STORE_ENABLED:
        return

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_training_data (
                  id BIGSERIAL PRIMARY KEY,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  model_used TEXT,
                  original_sql TEXT,
                  normalized_sql TEXT,
                  parsed_sql JSONB,
                  plan_summary JSONB,
                  rule_findings JSONB,
                  index_recommendations JSONB,
                  optimization_score JSONB,
                  llm_payload JSONB,
                  llm_output JSONB,
                  run_analyze BOOLEAN,
                  run_preview BOOLEAN,
                  warnings JSONB,
                  feedback_label TEXT,
                  feedback_notes TEXT,
                  feedback_updated_at TIMESTAMPTZ
                );
                """
            )
            cur.execute(
                "ALTER TABLE llm_training_data ADD COLUMN IF NOT EXISTS feedback_label TEXT"
            )
            cur.execute(
                "ALTER TABLE llm_training_data ADD COLUMN IF NOT EXISTS feedback_notes TEXT"
            )
            cur.execute(
                "ALTER TABLE llm_training_data ADD COLUMN IF NOT EXISTS feedback_updated_at TIMESTAMPTZ"
            )
            conn.commit()


def store_training_example(payload: Dict[str, Any]) -> None:
    """Save one analysis result to the database."""
    if not TRAINING_STORE_ENABLED:
        return

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO llm_training_data (
                  model_used,
                  original_sql,
                  normalized_sql,
                  parsed_sql,
                  plan_summary,
                  rule_findings,
                  index_recommendations,
                  optimization_score,
                  llm_payload,
                  llm_output,
                  run_analyze,
                  run_preview,
                  warnings
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    payload.get("model_used"),
                    payload.get("original_sql"),
                    payload.get("normalized_sql"),
                    Json(payload.get("parsed_sql") or {}),
                    Json(payload.get("plan_summary") or {}),
                    Json(payload.get("rule_findings") or []),
                    Json(payload.get("index_recommendations") or []),
                    Json(payload.get("optimization_score") or {}),
                    Json(payload.get("llm_payload") or {}),
                    Json(payload.get("llm_output") or {}),
                    payload.get("run_analyze"),
                    payload.get("run_preview"),
                    Json(payload.get("warnings") or []),
                ),
            )
            conn.commit()


def _build_filters(
    label: str | None = None,
    model: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    days: int | None = None,
) -> tuple[str, list[Any]]:
    """Build SQL filters from optional query parameters."""
    clauses = []
    params: list[Any] = []

    if label:
        if label == "unlabeled":
            clauses.append("(feedback_label IS NULL OR feedback_label = '')")
        else:
            clauses.append("feedback_label = %s")
            params.append(label)

    if model:
        clauses.append("model_used = %s")
        params.append(model)

    if date_from:
        clauses.append("created_at >= %s::date")
        params.append(date_from)

    if date_to:
        clauses.append("created_at < (%s::date + INTERVAL '1 day')")
        params.append(date_to)

    if days:
        clauses.append("created_at >= NOW() - (%s || ' days')::interval")
        params.append(str(int(days)))

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params


def list_training_examples(
    limit: int = 30,
    offset: int = 0,
    label: str | None = None,
    model: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    unlabeled_first: bool = False,
) -> list[Dict[str, Any]]:
    """Return recent training rows for the UI to show."""
    if not TRAINING_STORE_ENABLED:
        return []

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            where, params = _build_filters(label, model, date_from, date_to)
            order = "ORDER BY id DESC"
            if unlabeled_first:
                order = (
                    "ORDER BY (CASE WHEN feedback_label IS NULL OR feedback_label = ''"
                    " THEN 0 ELSE 1 END), id DESC"
                )
            cur.execute(
                f"""
                SELECT
                  id,
                  created_at,
                  model_used,
                  original_sql,
                  llm_output->>'suggested_sql' AS suggested_sql,
                  llm_output->>'explanation' AS explanation,
                  optimization_score->>'score' AS score,
                  optimization_score->>'grade' AS grade,
                  feedback_label,
                  feedback_notes
                FROM llm_training_data
                {where}
                {order}
                LIMIT %s OFFSET %s
                """,
                (*params, limit, offset),
            )
            rows = cur.fetchall()

    results = []
    for row in rows:
        results.append(
            {
                "id": row[0],
                "created_at": row[1].isoformat() if row[1] else None,
                "model_used": row[2],
                "original_sql": row[3],
                "suggested_sql": row[4],
                "explanation": row[5],
                "score": float(row[6]) if row[6] else None,
                "grade": row[7],
                "feedback_label": row[8],
                "feedback_notes": row[9],
            }
        )
    return results


def get_training_stats(
    label: str | None = None,
    model: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> Dict[str, Any]:
    """Return a tiny dashboard of training data stats."""
    if not TRAINING_STORE_ENABLED:
        return {}

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            where, params = _build_filters(label, model, date_from, date_to)

            cur.execute(f"SELECT COUNT(*) FROM llm_training_data {where}", params)
            total = cur.fetchone()[0]

            cur.execute(
                f"""
                SELECT model_used, COUNT(*)
                FROM llm_training_data
                {where}
                GROUP BY model_used
                ORDER BY COUNT(*) DESC
                """,
                params,
            )
            by_model = {row[0] or "unknown": row[1] for row in cur.fetchall()}

            cur.execute(
                f"""
                SELECT optimization_score->>'grade' AS grade, COUNT(*)
                FROM llm_training_data
                {where}
                GROUP BY optimization_score->>'grade'
                """,
                params,
            )
            by_grade = {row[0] or "n/a": row[1] for row in cur.fetchall()}

            cur.execute(
                f"""
                SELECT feedback_label, COUNT(*)
                FROM llm_training_data
                {where}
                GROUP BY feedback_label
                """,
                params,
            )
            by_label = {row[0] or "unlabeled": row[1] for row in cur.fetchall()}

            cur.execute(
                f"""
                SELECT AVG((optimization_score->>'score')::float)
                FROM llm_training_data
                {where + (" AND " if where else "WHERE ") + "optimization_score ? 'score'"}
                """,
                params,
            )
            avg_score = cur.fetchone()[0]

            cur.execute(
                f"""
                SELECT
                  AVG((optimization_score->>'score')::float)
                FROM llm_training_data
                {where + (" AND " if where else "WHERE ") + "feedback_label = 'good' AND optimization_score ? 'score'"}
                """,
                params,
            )
            avg_score_good = cur.fetchone()[0]

            cur.execute(
                f"""
                SELECT
                  AVG((optimization_score->>'score')::float)
                FROM llm_training_data
                {where + (" AND " if where else "WHERE ") + "feedback_label = 'bad' AND optimization_score ? 'score'"}
                """,
                params,
            )
            avg_score_bad = cur.fetchone()[0]

    return {
        "total": total,
        "by_model": by_model,
        "by_grade": by_grade,
        "by_label": by_label,
        "avg_score": round(avg_score, 2) if avg_score is not None else None,
        "avg_score_good": round(avg_score_good, 2) if avg_score_good is not None else None,
        "avg_score_bad": round(avg_score_bad, 2) if avg_score_bad is not None else None,
    }


def update_feedback(example_id: int, label: str, notes: str | None = None) -> None:
    """Save a human label so we can train later."""
    if not TRAINING_STORE_ENABLED:
        return

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE llm_training_data
                SET feedback_label = %s,
                    feedback_notes = %s,
                    feedback_updated_at = NOW()
                WHERE id = %s
                """,
                (label, notes, example_id),
            )
            conn.commit()


def export_training_data(
    limit: int = 1000,
    label: str | None = None,
    model: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[Dict[str, Any]]:
    """Return full training rows for export."""
    if not TRAINING_STORE_ENABLED:
        return []

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            where, params = _build_filters(label, model, date_from, date_to)
            cur.execute(
                f"""
                SELECT
                  id,
                  created_at,
                  model_used,
                  original_sql,
                  normalized_sql,
                  parsed_sql,
                  plan_summary,
                  rule_findings,
                  index_recommendations,
                  optimization_score,
                  llm_payload,
                  llm_output,
                  run_analyze,
                  run_preview,
                  warnings,
                  feedback_label,
                  feedback_notes,
                  feedback_updated_at
                FROM llm_training_data
                {where}
                ORDER BY id DESC
                LIMIT %s
                """,
                (*params, limit),
            )
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]

    results = []
    for row in rows:
        item = {}
        for idx, col in enumerate(columns):
            value = row[idx]
            if hasattr(value, "isoformat"):
                item[col] = value.isoformat()
            else:
                item[col] = value
        results.append(item)

    return results


def get_training_trends(
    days: int = 30,
    label: str | None = None,
    model: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[Dict[str, Any]]:
    """Return average score per day for a simple trend chart."""
    if not TRAINING_STORE_ENABLED:
        return []

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            where, params = _build_filters(label, model, date_from, date_to, days=days)
            cur.execute(
                f"""
                SELECT
                  date_trunc('day', created_at) AS day,
                  AVG((optimization_score->>'score')::float) AS avg_score,
                  COUNT(*) AS count
                FROM llm_training_data
                {where}
                GROUP BY day
                ORDER BY day
                """,
                params,
            )
            rows = cur.fetchall()

    results = []
    for row in rows:
        results.append(
            {
                "day": row[0].date().isoformat() if row[0] else None,
                "avg_score": round(row[1], 2) if row[1] is not None else None,
                "count": row[2],
            }
        )
    return results
