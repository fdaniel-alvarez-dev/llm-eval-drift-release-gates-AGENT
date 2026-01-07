from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GoldenCase(BaseModel):
    id: str
    intent: str
    question: str
    context: str
    expected_points: list[str]
    must_refuse: bool
    cost_per_answer: float | None = None


class CaseScores(BaseModel):
    correctness: float = Field(ge=0.0, le=1.0)
    groundedness: float = Field(ge=0.0, le=1.0)


class EvalCaseResult(BaseModel):
    id: str
    intent: str
    question: str
    context: str
    expected_points: list[str]
    must_refuse: bool
    answer: str
    citations: list[str]
    latency_ms: float = Field(ge=0.0)
    latency_source: Literal["synthetic", "measured"]
    cost_per_answer: float = Field(ge=0.0)
    scores: CaseScores
    safety_flags: list[str]


class ReportMeta(BaseModel):
    tool_name: str
    tool_version: str
    dataset_path: str
    dataset_sha256: str
    run_utc: datetime


class ReportSummary(BaseModel):
    case_count: int = Field(ge=1)
    overall_score: float = Field(ge=0.0, le=1.0)
    avg_correctness: float = Field(ge=0.0, le=1.0)
    avg_groundedness: float = Field(ge=0.0, le=1.0)
    safety_violation_rate: float = Field(ge=0.0, le=1.0)
    latency_p50_ms: float = Field(ge=0.0)
    latency_p95_ms: float = Field(ge=0.0)
    cost_per_answer_avg: float = Field(ge=0.0)


class EvalReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    meta: ReportMeta
    cases: list[EvalCaseResult]
    summary: ReportSummary

