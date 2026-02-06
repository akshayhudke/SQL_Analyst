"""Pydantic models used to validate API inputs and outputs."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Input from the UI when a user wants analysis."""
    sql: str = Field(..., min_length=1)
    run_analyze: bool = True
    run_preview: bool = True
    analysis_mode: str = Field("manual", pattern="^(live|manual)$")


class RuleFinding(BaseModel):
    """One rule-based finding with a clear recommendation."""
    id: str
    title: str
    severity: int
    rationale: str
    recommendation: str
    evidence: Optional[Dict[str, Any]] = None


class PlanSummary(BaseModel):
    """Small summary of a PostgreSQL plan."""
    planning_time_ms: Optional[float] = None
    execution_time_ms: Optional[float] = None
    total_cost: Optional[float] = None
    actual_rows: Optional[float] = None
    actual_total_time: Optional[float] = None
    node_counts: Dict[str, int]
    join_types: List[str]
    top_nodes: List[Dict[str, Any]]


class LLMOutput(BaseModel):
    """What the LLM responded with."""
    explanation: str
    suggested_sql: Optional[str] = None
    recommendation_rationale: Optional[str] = None
    error: Optional[str] = None
    rewrite_source: Optional[str] = None
    model_used: Optional[str] = None


class QueryPreview(BaseModel):
    """Tiny preview of result rows so users can sanity-check output."""
    columns: List[str]
    rows: List[List[Any]]
    row_count: int


class AnalyzeResponse(BaseModel):
    """Full response payload sent back to the UI."""
    parsed_sql: Dict[str, Any]
    plan_summary: Optional[PlanSummary]
    rule_findings: List[RuleFinding]
    llm: Optional[LLMOutput]
    preview: Optional[QueryPreview]
    raw_plan: Optional[Dict[str, Any]]
    warnings: List[str]
