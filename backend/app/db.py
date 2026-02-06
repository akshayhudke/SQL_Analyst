from typing import Any, Dict, List, Tuple
import psycopg

from .settings import ANALYZE_STATEMENT_TIMEOUT_MS, DATABASE_URL, PREVIEW_LIMIT


def _set_read_only(cursor: psycopg.Cursor) -> None:
    """Start a read-only transaction so we do not change data."""
    cursor.execute("BEGIN")
    cursor.execute("SET TRANSACTION READ ONLY")
    timeout_ms = int(ANALYZE_STATEMENT_TIMEOUT_MS)
    cursor.execute(f"SET LOCAL statement_timeout = {timeout_ms}")


def run_preview(sql: str, limit: int = PREVIEW_LIMIT) -> Dict[str, Any]:
    """Run a tiny preview of rows so you can see the shape of results."""
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            try:
                _set_read_only(cur)
                cur.execute(f"SELECT * FROM ({sql}) AS _preview LIMIT {limit}")
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                cur.execute("ROLLBACK")
            except Exception:
                cur.execute("ROLLBACK")
                raise

    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
    }


def explain_query(sql: str, analyze: bool = True) -> Dict[str, Any]:
    """Ask PostgreSQL for an execution plan (and optionally real timings)."""
    explain_options = "ANALYZE, BUFFERS, FORMAT JSON" if analyze else "FORMAT JSON"
    explain_sql = f"EXPLAIN ({explain_options}) {sql}"

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            try:
                _set_read_only(cur)
                cur.execute(explain_sql)
                result = cur.fetchone()[0]
                cur.execute("ROLLBACK")
            except Exception:
                cur.execute("ROLLBACK")
                raise

    plan = result[0] if isinstance(result, list) else result
    return plan


def fetch_table_columns(tables: List[str]) -> Dict[str, List[str]]:
    """Get column names for the given tables from the database catalog."""
    if not tables:
        return {}

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            try:
                _set_read_only(cur)
                cur.execute(
                    """
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                      AND table_name = ANY(%s)
                    ORDER BY table_name, ordinal_position
                    """,
                    (tables,),
                )
                rows = cur.fetchall()
                cur.execute("ROLLBACK")
            except Exception:
                cur.execute("ROLLBACK")
                raise

    columns: Dict[str, List[str]] = {}
    for table_name, column_name in rows:
        columns.setdefault(table_name, []).append(column_name)

    return columns
