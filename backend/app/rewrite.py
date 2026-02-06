"""Small, safe SQL rewrites that do not change meaning."""

from typing import Any, Dict, List, Optional, Tuple
import re


def _build_columns(
    parsed_sql: Dict[str, Any],
    columns_by_table: Dict[str, List[str]],
) -> Optional[List[str]]:
    """Build a list of fully-qualified columns using table aliases."""
    table_aliases = parsed_sql.get("table_aliases", [])
    if not table_aliases:
        return None

    columns: List[str] = []
    for entry in table_aliases:
        table_name = entry.get("table")
        alias = entry.get("alias") or table_name
        if not table_name or table_name not in columns_by_table:
            return None
        for column in columns_by_table[table_name]:
            if alias:
                columns.append(f"{alias}.{column}")
            else:
                columns.append(column)

    return columns or None


def rewrite_query(
    original_sql: str,
    parsed_sql: Dict[str, Any],
    columns_by_table: Dict[str, List[str]],
) -> Tuple[Optional[str], List[str]]:
    """Rewrite SELECT * into explicit columns while preserving formatting."""
    notes: List[str] = []

    if not parsed_sql.get("has_select_star"):
        return None, notes

    select_columns = parsed_sql.get("select_columns") or []
    if len(select_columns) != 1 or select_columns[0].strip() != "*":
        return None, notes

    columns = _build_columns(parsed_sql, columns_by_table)
    if not columns:
        return None, notes

    match = re.search(r"(?is)\bselect\b(?P<select_list>.*?)(?=\bfrom\b)", original_sql)
    if not match:
        return None, notes

    select_list = match.group("select_list")
    if select_list.strip() != "*":
        return None, notes

    star_index = select_list.find("*")
    if star_index == -1:
        return None, notes

    prefix = select_list[:star_index]
    suffix = select_list[star_index + 1 :]

    indent = ""
    if "\n" in prefix:
        indent = prefix.split("\n")[-1]
        joiner = ",\n" + indent
    else:
        joiner = ", "

    columns_joined = joiner.join(columns)
    new_select_list = prefix + columns_joined + suffix

    rewritten = (
        original_sql[: match.start("select_list")] +
        new_select_list +
        original_sql[match.end("select_list") :]
    )

    notes.append("Expanded SELECT * into explicit columns using schema metadata.")
    return rewritten, notes
