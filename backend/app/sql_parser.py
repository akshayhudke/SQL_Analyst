"""Parse SQL into simple facts that rules and the LLM can understand."""

from typing import Any, Dict, Tuple
import re
import sqlglot
from sqlglot import exp


_DISALLOWED_NAMES = [
    "Insert",
    "Update",
    "Delete",
    "Create",
    "Drop",
    "Alter",
    "AlterTable",
    "Truncate",
    "Replace",
    "Merge",
    "Analyze",
    "Explain",
]

DISALLOWED = tuple(getattr(exp, name, None) for name in _DISALLOWED_NAMES)
SQL_CODE_BLOCK_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
SQL_START_RE = re.compile(
    r"\b(SELECT|WITH|UPDATE|DELETE|INSERT|CREATE|ALTER|DROP|MERGE|TRUNCATE)\b",
    re.IGNORECASE,
)


def _norm_expr(value: str) -> str:
    """Normalize expression text for set comparisons."""
    return " ".join(value.lower().strip().split())


def _extract_sql_candidate(text: str) -> str:
    """Extract likely SQL statement from raw user text (supports markdown blocks)."""
    candidate = text.strip()
    if not candidate:
        return candidate

    block_match = SQL_CODE_BLOCK_RE.search(candidate)
    if block_match:
        candidate = block_match.group(1).strip()

    start_match = SQL_START_RE.search(candidate)
    if start_match and start_match.start() > 0:
        candidate = candidate[start_match.start() :].strip()

    return candidate


def _has_disallowed(expression: exp.Expression) -> bool:
    """Return True if the query tries to change data (we allow read-only only)."""
    disallowed = tuple(item for item in DISALLOWED if item is not None)
    if not disallowed:
        return False
    return any(expression.find_all(disallowed))


def parse_sql(sql: str) -> Tuple[str, Dict[str, Any]]:
    """Turn SQL text into a clean SQL string plus an easy-to-read summary.

    This parser accepts any single SQL statement. Read-only SELECT queries are
    marked as execution-safe; other query types are analyzed statically.
    """
    sql = _extract_sql_candidate(sql)
    try:
        expressions = sqlglot.parse(sql, read="postgres")
    except Exception as exc:
        try:
            # Fallback parser helps with non-Postgres syntax from other dialects.
            expressions = sqlglot.parse(sql)
        except Exception:
            raise ValueError(f"Invalid SQL: {exc}") from exc
    if len(expressions) != 1:
        raise ValueError("Only a single SQL statement is supported in the MVP.")

    expression = expressions[0]
    is_read_only = not _has_disallowed(expression)
    statement_type = str(getattr(expression, "key", "") or expression.__class__.__name__).upper()

    select = expression.find(exp.Select)
    has_select = select is not None
    supports_execution = bool(is_read_only and has_select)

    try:
        normalized_sql = expression.sql(dialect="postgres")
    except Exception:
        normalized_sql = expression.sql()

    select_columns = []
    has_select_star = False
    non_agg_select_expressions = []
    has_aggregate_expression = False
    if select is not None and select.expressions:
        for item in select.expressions:
            select_columns.append(item.sql(dialect="postgres"))
            if isinstance(item, exp.Star):
                has_select_star = True
            expr = item.this if isinstance(item, exp.Alias) else item
            if isinstance(expr, (exp.Literal, exp.Boolean, exp.Null)):
                continue
            if expr.find(exp.AggFunc) is not None or isinstance(expr, exp.AggFunc):
                has_aggregate_expression = True
                continue
            non_agg_select_expressions.append(expr.sql(dialect="postgres"))

    tables_ordered = []
    table_aliases = []
    seen_tables = set()
    for table in expression.find_all(exp.Table):
        if not table.name:
            continue
        if table.name not in seen_tables:
            tables_ordered.append(table.name)
            seen_tables.add(table.name)

        alias_expr = table.args.get("alias")
        alias_name = None
        if alias_expr is not None:
            alias_name = getattr(alias_expr, "name", None)
        table_aliases.append({"table": table.name, "alias": alias_name})

    tables = sorted(seen_tables)
    cte_names = []
    for cte in expression.find_all(exp.CTE):
        alias = cte.args.get("alias")
        alias_name = getattr(alias, "name", None)
        if alias_name:
            cte_names.append(alias_name)

    where = expression.find(exp.Where)
    where_text = where.this.sql(dialect="postgres") if where is not None else None
    has_where = where is not None

    functions_in_where = []
    if where is not None:
        for func in where.find_all(exp.Func):
            if func.find(exp.Column) is not None:
                functions_in_where.append(func.sql(dialect="postgres"))
        for func in where.find_all(exp.Anonymous):
            if func.find(exp.Column) is not None:
                functions_in_where.append(func.sql(dialect="postgres"))

    joins = []
    join_conditions = []
    for join in expression.find_all(exp.Join):
        kind = join.args.get("kind")
        joins.append((kind or "INNER").upper())
        on_expr = join.args.get("on")
        if on_expr is not None:
            join_conditions.append(on_expr.sql(dialect="postgres"))

    order = expression.find(exp.Order)
    order_by = []
    if order is not None:
        order_by = [item.sql(dialect="postgres") for item in order.expressions]

    group = expression.find(exp.Group)
    group_by = []
    has_group_ordinal = False
    if group is not None:
        group_by = [item.sql(dialect="postgres") for item in group.expressions]
        has_group_ordinal = any(
            isinstance(item, exp.Literal) and item.is_int for item in group.expressions
        )

    group_set = {_norm_expr(item) for item in group_by}
    group_by_missing_expressions = []
    if has_aggregate_expression and non_agg_select_expressions and not has_group_ordinal:
        if not group_set:
            group_by_missing_expressions = list(non_agg_select_expressions)
        else:
            for expr_sql in non_agg_select_expressions:
                if _norm_expr(expr_sql) not in group_set:
                    group_by_missing_expressions.append(expr_sql)
    elif group_set and not has_group_ordinal:
        for expr_sql in non_agg_select_expressions:
            if _norm_expr(expr_sql) not in group_set:
                group_by_missing_expressions.append(expr_sql)

    limit = expression.find(exp.Limit)
    limit_value = limit.expression.sql(dialect="postgres") if limit is not None else None

    has_distinct = bool(select and select.args.get("distinct"))
    has_cte = expression.find(exp.With) is not None
    has_subquery = expression.find(exp.Subquery) is not None
    has_or = where is not None and bool(list(where.find_all(exp.Or)))
    in_subqueries = []
    for in_expr in expression.find_all(exp.In):
        if list(in_expr.find_all(exp.Subquery)) or in_expr.args.get("query") is not None:
            in_subqueries.append(in_expr.sql(dialect="postgres"))

    parsed = {
        "normalized_sql": normalized_sql,
        "statement_type": statement_type,
        "is_read_only": is_read_only,
        "has_select": has_select,
        "supports_execution": supports_execution,
        "tables": tables,
        "cte_names": sorted(set(cte_names)),
        "tables_ordered": tables_ordered,
        "table_aliases": table_aliases,
        "select_columns": select_columns,
        "non_agg_select_expressions": non_agg_select_expressions,
        "has_aggregate_expression": has_aggregate_expression,
        "has_select_star": has_select_star,
        "has_where": has_where,
        "where": where_text,
        "functions_in_where": functions_in_where,
        "joins": joins,
        "join_conditions": join_conditions,
        "order_by": order_by,
        "group_by": group_by,
        "has_group_ordinal": has_group_ordinal,
        "group_by_missing_expressions": group_by_missing_expressions,
        "limit": limit_value,
        "has_distinct": has_distinct,
        "has_cte": has_cte,
        "has_subquery": has_subquery,
        "has_or": has_or,
        "in_subqueries": in_subqueries,
        "subquery_count": len(list(expression.find_all(exp.Subquery))),
    }

    return normalized_sql, parsed
