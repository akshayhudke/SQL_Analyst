"""Small, safe SQL rewrites that do not change meaning."""

from typing import Any, Dict, List, Optional, Tuple
import re
import sqlglot
from sqlglot import exp


def _norm_expr(value: str) -> str:
    """Normalize expression text for comparisons."""
    return " ".join(value.lower().strip().split())


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


def _rewrite_group_by_mismatch(
    original_sql: str,
    parsed_sql: Dict[str, Any],
) -> Tuple[Optional[str], List[str]]:
    """Fix invalid GROUP BY by aligning grouped expressions with selected columns."""
    notes: List[str] = []
    missing = parsed_sql.get("group_by_missing_expressions") or []
    if not missing:
        return None, notes
    if parsed_sql.get("has_group_ordinal"):
        return None, notes

    try:
        expression = sqlglot.parse_one(original_sql, read="postgres")
    except Exception:
        expression = sqlglot.parse_one(original_sql)

    non_agg = parsed_sql.get("non_agg_select_expressions") or []
    group_by = parsed_sql.get("group_by") or []
    group = expression.find(exp.Group)
    if group is None and non_agg:
        group = exp.Group(
            expressions=[
                sqlglot.parse_one(f"SELECT {expr_sql}", read="postgres").find(exp.Select).expressions[0]
                for expr_sql in non_agg
            ]
        )
        select = expression.find(exp.Select)
        if select is None:
            return None, notes
        select.set("group", group)
        notes.append("Added GROUP BY for non-aggregated SELECT expressions.")
        return expression.sql(dialect="postgres"), notes
    if group is None:
        return None, notes

    non_agg_set = {_norm_expr(item) for item in non_agg}
    group_set = {_norm_expr(item) for item in group_by}

    new_group_expressions: List[exp.Expression] = []
    if non_agg and group_set and all(item not in non_agg_set for item in group_set):
        for expr_sql in non_agg:
            parsed_expr = sqlglot.parse_one(f"SELECT {expr_sql}", read="postgres").find(exp.Select).expressions[0]
            new_group_expressions.append(parsed_expr)
        notes.append("Replaced GROUP BY with non-aggregated SELECT expressions to fix invalid aggregation.")
    else:
        for item in group.expressions:
            new_group_expressions.append(item)
        existing = {_norm_expr(item.sql(dialect="postgres")) for item in group.expressions}
        for expr_sql in missing:
            if _norm_expr(expr_sql) in existing:
                continue
            parsed_expr = sqlglot.parse_one(f"SELECT {expr_sql}", read="postgres").find(exp.Select).expressions[0]
            new_group_expressions.append(parsed_expr)
        notes.append("Added missing non-aggregated SELECT expressions to GROUP BY.")

    group.set("expressions", new_group_expressions)
    return expression.sql(dialect="postgres"), notes


def _rewrite_select_star(
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


def rewrite_query(
    original_sql: str,
    parsed_sql: Dict[str, Any],
    columns_by_table: Dict[str, List[str]],
) -> Tuple[Optional[str], List[str]]:
    """Apply safe deterministic rewrites and return the best fixed query."""
    notes: List[str] = []
    candidate = original_sql
    changed = False

    group_rewrite, group_notes = _rewrite_group_by_mismatch(candidate, parsed_sql)
    if group_rewrite and group_rewrite.strip() != candidate.strip():
        candidate = group_rewrite
        notes.extend(group_notes)
        changed = True

    star_rewrite, star_notes = _rewrite_select_star(candidate, parsed_sql, columns_by_table)
    if star_rewrite and star_rewrite.strip() != candidate.strip():
        candidate = star_rewrite
        notes.extend(star_notes)
        changed = True

    return (candidate if changed else None), notes
