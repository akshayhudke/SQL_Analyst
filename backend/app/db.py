from typing import Any, Dict, List, Tuple
import re
import psycopg

from .settings import ANALYZE_STATEMENT_TIMEOUT_MS, DATABASE_URL, PREVIEW_LIMIT


_INDEX_COLUMNS_RE = re.compile(r"\(([^()]*)\)")


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


def fetch_schema_metadata(tables: List[str]) -> Dict[str, Dict[str, Any]]:
    """Fetch table columns and index metadata from PostgreSQL catalogs."""
    if not tables:
        return {}

    metadata: Dict[str, Dict[str, Any]] = {}
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            try:
                _set_read_only(cur)
                cur.execute(
                    """
                    SELECT
                      table_name,
                      column_name,
                      data_type,
                      udt_name,
                      is_nullable = 'YES' AS is_nullable
                    FROM information_schema.columns
                    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                      AND table_name = ANY(%s)
                    ORDER BY table_name, ordinal_position
                    """,
                    (tables,),
                )
                column_rows = cur.fetchall()

                cur.execute(
                    """
                    SELECT
                      t.relname AS table_name,
                      i.relname AS index_name,
                      ix.indisunique AS is_unique,
                      ix.indisprimary AS is_primary,
                      pg_get_indexdef(i.oid) AS index_def
                    FROM pg_class t
                    JOIN pg_namespace n ON n.oid = t.relnamespace
                    JOIN pg_index ix ON ix.indrelid = t.oid
                    JOIN pg_class i ON i.oid = ix.indexrelid
                    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                      AND t.relname = ANY(%s)
                    ORDER BY t.relname, i.relname
                    """,
                    (tables,),
                )
                index_rows = cur.fetchall()
                cur.execute("ROLLBACK")
            except Exception:
                cur.execute("ROLLBACK")
                raise

    for table_name, column_name, data_type, udt_name, is_nullable in column_rows:
        table_info = metadata.setdefault(
            table_name,
            {"columns": [], "indexes": []},
        )
        table_info["columns"].append(
            {
                "name": column_name,
                "data_type": data_type,
                "udt_name": udt_name,
                "nullable": bool(is_nullable),
            }
        )

    for table_name, index_name, is_unique, is_primary, index_def in index_rows:
        table_info = metadata.setdefault(
            table_name,
            {"columns": [], "indexes": []},
        )
        match = _INDEX_COLUMNS_RE.search(index_def or "")
        raw_columns = match.group(1) if match else ""
        columns = [item.strip().strip('"') for item in raw_columns.split(",") if item.strip()]
        table_info["indexes"].append(
            {
                "name": index_name,
                "is_unique": bool(is_unique),
                "is_primary": bool(is_primary),
                "columns": columns,
                "definition": index_def,
            }
        )

    return metadata


def fetch_table_statistics(tables: List[str]) -> Dict[str, Dict[str, Any]]:
    """Fetch row-count and storage statistics used for optimization hints."""
    if not tables:
        return {}

    stats: Dict[str, Dict[str, Any]] = {}
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            try:
                _set_read_only(cur)
                cur.execute(
                    """
                    SELECT
                      c.relname AS table_name,
                      c.reltuples::bigint AS estimated_rows,
                      pg_total_relation_size(c.oid) AS total_bytes,
                      COALESCE(s.n_live_tup, 0)::bigint AS live_rows,
                      COALESCE(s.n_dead_tup, 0)::bigint AS dead_rows,
                      s.last_analyze,
                      s.last_autoanalyze
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
                    WHERE c.relkind = 'r'
                      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                      AND c.relname = ANY(%s)
                    ORDER BY c.relname
                    """,
                    (tables,),
                )
                rows = cur.fetchall()
                cur.execute("ROLLBACK")
            except Exception:
                cur.execute("ROLLBACK")
                raise

    for row in rows:
        (
            table_name,
            estimated_rows,
            total_bytes,
            live_rows,
            dead_rows,
            last_analyze,
            last_autoanalyze,
        ) = row
        stats[table_name] = {
            "estimated_rows": int(estimated_rows or 0),
            "total_bytes": int(total_bytes or 0),
            "live_rows": int(live_rows or 0),
            "dead_rows": int(dead_rows or 0),
            "last_analyze": last_analyze.isoformat() if last_analyze else None,
            "last_autoanalyze": last_autoanalyze.isoformat() if last_autoanalyze else None,
        }

    return stats
