"""Rule-based checks that explain common SQL performance problems."""

from typing import Any, Dict, List
import re

from .plan_summary import iter_plan_nodes


COLUMN_REGEX = re.compile(r"([a-zA-Z_][\w\.]*)\s*(=|<|>|<=|>=|!=|<>|ILIKE|LIKE|IN|ANY)")


def _add(
    findings: List[Dict[str, Any]],
    rule_id: str,
    title: str,
    severity: int,
    rationale: str,
    recommendation: str,
    evidence: Dict[str, Any] | None = None,
) -> None:
    """Add one rule finding to the list."""
    findings.append(
        {
            "id": rule_id,
            "title": title,
            "severity": severity,
            "rationale": rationale,
            "recommendation": recommendation,
            "evidence": evidence or {},
        }
    )


def _extract_columns(filter_text: str) -> List[str]:
    """Pull column names out of a simple WHERE or JOIN condition."""
    if not filter_text:
        return []
    return sorted({match[0] for match in COLUMN_REGEX.findall(filter_text)})


def _map_columns_to_tables(
    columns: List[str],
    table_aliases: List[Dict[str, Any]],
    tables: List[str],
    columns_by_table: Dict[str, List[str]] | None = None,
) -> Dict[str, List[str]]:
    """Match column names to tables using aliases, like a tiny lookup map."""
    alias_map = {}
    for entry in table_aliases or []:
        table_name = entry.get("table")
        alias = entry.get("alias") or table_name
        if table_name and alias:
            alias_map[alias] = table_name
            alias_map[table_name] = table_name

    table_columns: Dict[str, List[str]] = {}
    for col in columns:
        col = col.strip().strip('"')
        if "." in col:
            alias, col_name = col.split(".", 1)
            table = alias_map.get(alias)
        else:
            col_name = col
            table = tables[0] if len(tables) == 1 else None
        if not table:
            continue
        if columns_by_table and col_name not in columns_by_table.get(table, []):
            continue
        table_columns.setdefault(table, [])
        if col_name not in table_columns[table]:
            table_columns[table].append(col_name)

    return table_columns


def build_index_recommendations(
    parsed_sql: Dict[str, Any],
    columns_by_table: Dict[str, List[str]] | None = None,
) -> List[Dict[str, Any]]:
    """Suggest index statements from join and filter columns."""
    join_columns: List[str] = []
    for condition in parsed_sql.get("join_conditions") or []:
        join_columns.extend(_extract_columns(condition))

    filter_columns = _extract_columns(parsed_sql.get("where") or "")

    join_by_table = _map_columns_to_tables(
        join_columns,
        parsed_sql.get("table_aliases") or [],
        parsed_sql.get("tables") or [],
        columns_by_table,
    )
    filter_by_table = _map_columns_to_tables(
        filter_columns,
        parsed_sql.get("table_aliases") or [],
        parsed_sql.get("tables") or [],
        columns_by_table,
    )

    recommendations: List[Dict[str, Any]] = []
    for table in sorted(set((parsed_sql.get("tables") or []))):
        join_cols = [c for c in join_by_table.get(table, []) if c != "id"]
        filter_cols = [c for c in filter_by_table.get(table, []) if c != "id"]

        if not join_cols and not filter_cols:
            continue

        if join_cols and filter_cols:
            composite = join_cols + [c for c in filter_cols if c not in join_cols]
            index_name = f"idx_{table}_{'_'.join(composite)}"
            statement = f"CREATE INDEX {index_name} ON {table}({', '.join(composite)});"
            recommendations.append(
                {
                    "table": table,
                    "columns": composite,
                    "statement": statement,
                    "rationale": "Join + filter columns benefit from composite indexes.",
                }
            )
        else:
            for col in sorted(set(join_cols + filter_cols)):
                index_name = f"idx_{table}_{col}"
                statement = f"CREATE INDEX {index_name} ON {table}({col});"
                recommendations.append(
                    {
                        "table": table,
                        "columns": [col],
                        "statement": statement,
                        "rationale": "Filter or join column is a candidate for indexing.",
                    }
                )

    return recommendations


def score_findings(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Turn rule findings into a simple score and grade."""
    penalties = {1: 7, 2: 15, 3: 25}
    total_penalty = 0
    severity_counts = {1: 0, 2: 0, 3: 0}
    for finding in findings:
        severity = int(finding.get("severity", 1))
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        total_penalty += penalties.get(severity, 7)

    score = max(0, 100 - total_penalty)
    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 60:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": score,
        "grade": grade,
        "issue_count": len(findings),
        "severity_counts": severity_counts,
    }


def run_rules(parsed_sql: Dict[str, Any], plan_json: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    """Run all rule checks on SQL structure and plan output."""
    findings: List[Dict[str, Any]] = []

    if parsed_sql.get("has_select_star"):
        _add(
            findings,
            "sql_select_star",
            "Avoid SELECT *",
            1,
            "Selecting all columns increases IO and can block index-only scans.",
            "Select only the columns you need.",
            {"tables": parsed_sql.get("tables")},
        )

    if not parsed_sql.get("has_where"):
        _add(
            findings,
            "sql_no_where",
            "No WHERE clause",
            2,
            "Full table scans are common when no filters are applied.",
            "Add a selective WHERE clause if possible.",
            {"tables": parsed_sql.get("tables")},
        )

    if parsed_sql.get("order_by") and not parsed_sql.get("limit"):
        _add(
            findings,
            "sql_order_no_limit",
            "ORDER BY without LIMIT",
            1,
            "Sorting large result sets can be expensive when no row limit is set.",
            "Add LIMIT when only the top rows are needed.",
            {"order_by": parsed_sql.get("order_by")},
        )

    if parsed_sql.get("functions_in_where"):
        _add(
            findings,
            "sql_non_sargable",
            "Functions in WHERE clause",
            2,
            "Functions on columns can prevent index usage.",
            "Rewrite filters to avoid functions on indexed columns.",
            {"functions": parsed_sql.get("functions_in_where")},
        )

    filter_columns = _extract_columns(parsed_sql.get("where") or "")
    join_columns: List[str] = []
    for condition in parsed_sql.get("join_conditions") or []:
        join_columns.extend(_extract_columns(condition))
    index_candidates = sorted({*filter_columns, *join_columns})
    if index_candidates:
        _add(
            findings,
            "sql_index_candidates",
            "Index candidates from filters/joins",
            1,
            "Columns used in filters and joins are common index candidates.",
            "Consider indexes on: " + ", ".join(index_candidates),
            {"columns": index_candidates},
        )

    if parsed_sql.get("subquery_count", 0) > 0:
        _add(
            findings,
            "sql_subquery",
            "Nested subqueries detected",
            2,
            "Nested subqueries can prevent the planner from optimizing join order.",
            "Consider flattening subqueries into JOINs or EXISTS clauses.",
            {"count": parsed_sql.get("subquery_count")},
        )

    in_subqueries = parsed_sql.get("in_subqueries") or []
    if len(in_subqueries) >= 2:
        _add(
            findings,
            "sql_multiple_in_subqueries",
            "Multiple IN subqueries",
            2,
            "Multiple IN subqueries often execute repeatedly and scale poorly.",
            "Rewrite IN subqueries as JOINs or EXISTS with correlated predicates.",
            {"examples": in_subqueries},
        )

    if parsed_sql.get("in_subqueries"):
        _add(
            findings,
            "sql_in_subquery",
            "IN subqueries in WHERE",
            2,
            "IN subqueries can be slower than EXISTS or JOINs, especially with large datasets.",
            "Consider rewriting IN subqueries as EXISTS with correlated predicates or JOINs.",
            {"examples": parsed_sql.get("in_subqueries")},
        )

    if not parsed_sql.get("joins") and parsed_sql.get("in_subqueries"):
        _add(
            findings,
            "sql_subqueries_no_joins",
            "Subqueries used instead of JOINs",
            2,
            "Using multiple subqueries can prevent the optimizer from reordering joins efficiently.",
            "Rewrite subqueries into JOINs where possible to allow better join planning.",
            {"examples": parsed_sql.get("in_subqueries")},
        )

    if not plan_json:
        return findings

    root = plan_json.get("Plan", plan_json)

    for node in iter_plan_nodes(root):
        node_type = node.get("Node Type")
        actual_rows = node.get("Actual Rows") or 0
        plan_rows = node.get("Plan Rows") or 0

        if node_type == "Seq Scan" and actual_rows > 1000:
            filter_text = node.get("Filter")
            columns = _extract_columns(filter_text or "")
            if filter_text:
                _add(
                    findings,
                    "plan_seq_scan_filter",
                    "Sequential scan with filter",
                    2,
                    "A sequential scan filtered many rows; an index may help.",
                    "Consider an index on the filtered columns.",
                    {
                        "relation": node.get("Relation Name"),
                        "filter": filter_text,
                        "columns": columns,
                    },
                )
            else:
                _add(
                    findings,
                    "plan_seq_scan_no_filter",
                    "Sequential scan without filter",
                    2,
                    "A sequential scan over many rows suggests missing filters or limits.",
                    "Add a selective WHERE clause or LIMIT if possible.",
                    {"relation": node.get("Relation Name")},
                )

        if node_type == "Sort" and actual_rows > 1000:
            sort_key = node.get("Sort Key")
            sort_method = node.get("Sort Method")
            severity = 2 if sort_method and "external" in str(sort_method).lower() else 1
            _add(
                findings,
                "plan_large_sort",
                "Large sort operation",
                severity,
                "Sorting many rows can be expensive and may spill to disk.",
                "Add an index that matches the sort key or reduce rows earlier.",
                {
                    "sort_key": sort_key,
                    "sort_method": sort_method,
                },
            )

        if node_type == "Nested Loop" and actual_rows > 1000:
            _add(
                findings,
                "plan_nested_loop",
                "Large nested loop join",
                2,
                "Nested loop joins can be slow with large inputs.",
                "Consider indexes on join keys or rewriting for hash/merge joins.",
                {"join_type": node.get("Join Type")},
            )

        if node_type == "Hash" and node.get("Hash Batches") and node.get("Hash Batches") > 1:
            _add(
                findings,
                "plan_hash_spill",
                "Hash spill detected",
                2,
                "Hash operations spilled to disk, increasing latency.",
                "Increase work_mem or reduce input rows.",
                {
                    "hash_batches": node.get("Hash Batches"),
                    "peak_memory": node.get("Peak Memory Usage"),
                },
            )

        rows_removed = node.get("Rows Removed by Filter")
        if rows_removed and actual_rows and rows_removed > actual_rows * 2:
            _add(
                findings,
                "plan_filter_removed",
                "Many rows removed by filter",
                2,
                "A large share of rows were filtered after scan, indicating low selectivity.",
                "Consider a more selective predicate or an index supporting the filter.",
                {
                    "rows_removed": rows_removed,
                    "actual_rows": actual_rows,
                },
            )

        if plan_rows:
            ratio = actual_rows / plan_rows if plan_rows else 1
            if ratio > 10 or ratio < 0.1:
                _add(
                    findings,
                    "plan_estimate_mismatch",
                    "Row estimate mismatch",
                    1,
                    "Planner estimates are far from actual rows, which can lead to suboptimal plans.",
                    "Run ANALYZE on the involved tables to refresh statistics.",
                    {
                        "plan_rows": plan_rows,
                        "actual_rows": actual_rows,
                    },
                )

    return findings
