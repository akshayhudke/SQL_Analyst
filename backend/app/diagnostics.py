"""Collect schema and statistics metadata required by the SQL optimization agent."""

from typing import Any, Dict, List

from .db import fetch_schema_metadata, fetch_table_statistics


def collect_diagnostics(parsed_sql: Dict[str, Any]) -> Dict[str, Any]:
    """Gather schema, index, and table statistics for referenced base tables."""
    tables = parsed_sql.get("tables") or []
    schema_metadata = fetch_schema_metadata(tables)
    table_statistics = fetch_table_statistics(tables)

    columns_by_table: Dict[str, List[str]] = {}
    for table_name, table_info in schema_metadata.items():
        columns_by_table[table_name] = [
            column.get("name")
            for column in (table_info.get("columns") or [])
            if column.get("name")
        ]

    known_tables = set(schema_metadata.keys())
    cte_names = {name.lower() for name in (parsed_sql.get("cte_names") or [])}
    missing_tables = [
        table_name
        for table_name in tables
        if table_name not in known_tables and table_name.lower() not in cte_names
    ]

    supports_execution = bool(parsed_sql.get("supports_execution"))
    execution_allowed = supports_execution and not missing_tables

    return {
        "schema_metadata": schema_metadata,
        "table_statistics": table_statistics,
        "columns_by_table": columns_by_table,
        "missing_tables": missing_tables,
        "execution_allowed": execution_allowed,
    }
