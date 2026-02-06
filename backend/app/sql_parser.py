"""Parse SQL into simple facts that rules and the LLM can understand."""

from typing import Any, Dict, Tuple
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


def _has_disallowed(expression: exp.Expression) -> bool:
    """Return True if the query tries to change data (we allow read-only only)."""
    disallowed = tuple(item for item in DISALLOWED if item is not None)
    return any(expression.find_all(disallowed))


def parse_sql(sql: str) -> Tuple[str, Dict[str, Any]]:
    """Turn SQL text into a clean SQL string plus an easy-to-read summary."""
    try:
        expressions = sqlglot.parse(sql, read="postgres")
    except Exception as exc:
        raise ValueError(f"Invalid SQL: {exc}") from exc
    if len(expressions) != 1:
        raise ValueError("Only a single SQL statement is supported in the MVP.")

    expression = expressions[0]
    if _has_disallowed(expression):
        raise ValueError("Only read-only SELECT queries are supported in the MVP.")

    if not expression.find(exp.Select):
        raise ValueError("Only read-only SELECT queries are supported in the MVP.")

    normalized_sql = expression.sql(dialect="postgres")

    select = expression.find(exp.Select)
    select_columns = []
    has_select_star = False
    if select is not None and select.expressions:
        for item in select.expressions:
            select_columns.append(item.sql(dialect="postgres"))
            if isinstance(item, exp.Star):
                has_select_star = True

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

    where = expression.find(exp.Where)
    where_text = where.this.sql(dialect="postgres") if where is not None else None
    has_where = where is not None

    functions_in_where = []
    if where is not None:
        for func in where.find_all(exp.Func):
            functions_in_where.append(func.sql(dialect="postgres"))
        for func in where.find_all(exp.Anonymous):
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
    if group is not None:
        group_by = [item.sql(dialect="postgres") for item in group.expressions]

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
        "tables": tables,
        "tables_ordered": tables_ordered,
        "table_aliases": table_aliases,
        "select_columns": select_columns,
        "has_select_star": has_select_star,
        "has_where": has_where,
        "where": where_text,
        "functions_in_where": functions_in_where,
        "joins": joins,
        "join_conditions": join_conditions,
        "order_by": order_by,
        "group_by": group_by,
        "limit": limit_value,
        "has_distinct": has_distinct,
        "has_cte": has_cte,
        "has_subquery": has_subquery,
        "has_or": has_or,
        "in_subqueries": in_subqueries,
        "subquery_count": len(list(expression.find_all(exp.Subquery))),
    }

    return normalized_sql, parsed
