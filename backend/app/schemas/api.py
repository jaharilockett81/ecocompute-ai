"""Pydantic request schemas (responses are plain dicts built from stored records)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Category = Literal["extraction", "summarization", "classification", "structured_json", "reasoning", "coding", "data_interpretation", "general"]


class WorkloadRequest(BaseModel):
    task: str = Field(..., min_length=3, description="The prompt / task text")
    category: Category | None = None
    output_format: Literal["text", "json", "code"] = "text"
    quality_threshold: float = Field(0.8, ge=0.5, le=0.99)
    allow_escalation: bool = True
    max_escalations: int = Field(2, ge=0, le=2)
    repair_attempts: int = Field(0, ge=0, le=1)
    max_cost_usd: float | None = Field(None, gt=0, le=0.5)
    max_latency_ms: float | None = Field(None, gt=0, le=600_000)
    use_judge: bool = False
    forced_tier: str | None = None
    # Quality gate inputs (turned into deterministic checks)
    json_schema: dict | None = None
    required_fields: list[str] = Field(default_factory=list, max_length=30)
    expected_fields: dict | None = Field(None, description="dotted-path -> expected value (exact checks)")
    required_terms: list[str] = Field(default_factory=list, max_length=20)
    max_words: int | None = Field(None, ge=1, le=5000)
    exact_answer: str | None = Field(None, max_length=500)

    @field_validator("json_schema")
    @classmethod
    def _schema_size(cls, v: dict | None) -> dict | None:
        import json

        if v is not None and len(json.dumps(v)) > 20_000:
            raise ValueError("json_schema too large")
        return v

    def build_checks(self) -> list[dict]:
        checks: list[dict] = []
        if self.output_format == "json":
            schema = dict(self.json_schema or {})
            if self.required_fields:
                schema.setdefault("type", "object")
                schema["required"] = sorted(set(schema.get("required", [])) | set(self.required_fields))
            checks.append({"type": "json_schema", "schema": schema})
            if self.expected_fields:
                checks.append({"type": "json_fields", "expected": self.expected_fields})
        if self.required_terms:
            checks.append({"type": "contains_all", "terms": [t for t in self.required_terms if t.strip()]})
        if self.max_words:
            checks.append({"type": "word_limit", "max": self.max_words})
        if self.exact_answer:
            checks.append({"type": "exact", "answer": self.exact_answer})
        return checks


class BenchmarkRequest(BaseModel):
    conditions: list[str] = Field(default_factory=lambda: ["fixed:large", "adaptive"], min_length=1, max_length=5)
    split: Literal["test", "calib", "all"] = "test"
    categories: list[Category] | None = None
    case_ids: list[str] | None = Field(None, max_length=60)
    limit: int | None = Field(None, ge=1, le=60)
    repeats: int = Field(1, ge=1, le=3)
    max_calls: int | None = Field(None, ge=1, le=2000)


class PreviewRequest(BaseModel):
    task: str = Field(..., min_length=3)
    category: Category | None = None
    output_format: Literal["text", "json", "code"] = "text"
    quality_threshold: float = Field(0.8, ge=0.5, le=0.99)
    allow_escalation: bool = True
    max_cost_usd: float | None = Field(None, gt=0, le=0.5)
