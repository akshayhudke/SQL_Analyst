"""Summarize PostgreSQL plans into a small set of easy facts."""

from typing import Any, Dict, Iterable, List


def iter_plan_nodes(plan: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """Walk through every plan node, like walking all rooms in a treehouse."""
    stack = [plan]
    while stack:
        node = stack.pop()
        yield node
        for child in node.get("Plans", []):
            stack.append(child)


def summarize_plan(plan_json: Dict[str, Any]) -> Dict[str, Any]:
    """Pick out the most important plan numbers so the UI can show them."""
    if not plan_json:
        return {}

    root = plan_json.get("Plan", plan_json)
    node_counts: Dict[str, int] = {}
    join_types: List[str] = []
    top_nodes: List[Dict[str, Any]] = []

    for node in iter_plan_nodes(root):
        node_type = node.get("Node Type", "Unknown")
        node_counts[node_type] = node_counts.get(node_type, 0) + 1
        if "Join Type" in node:
            join_types.append(node.get("Join Type"))

    for node in iter_plan_nodes(root):
        top_nodes.append(
            {
                "node_type": node.get("Node Type"),
                "relation": node.get("Relation Name"),
                "actual_rows": node.get("Actual Rows"),
                "actual_total_time": node.get("Actual Total Time"),
                "rows_removed_by_filter": node.get("Rows Removed by Filter"),
            }
        )

    top_nodes = sorted(
        top_nodes,
        key=lambda item: (item.get("actual_total_time") or 0),
        reverse=True,
    )[:5]

    summary = {
        "planning_time_ms": plan_json.get("Planning Time"),
        "execution_time_ms": plan_json.get("Execution Time"),
        "total_cost": root.get("Total Cost"),
        "actual_rows": root.get("Actual Rows"),
        "actual_total_time": root.get("Actual Total Time"),
        "node_counts": node_counts,
        "join_types": sorted({jt for jt in join_types if jt}),
        "top_nodes": top_nodes,
    }

    return summary
