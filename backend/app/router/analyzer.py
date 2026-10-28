"""Workload analysis: transparent, rule-based feature extraction.

This is a heuristic, not a trained model. Every rule that fires is recorded
in `signals` so the decision trace shows exactly why a task was scored the
way it was.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

CATEGORIES = ("extraction", "summarization", "classification", "structured_json", "reasoning", "coding", "data_interpretation", "general")

# Expected answer length (completion tokens, excluding hidden reasoning) per category — a prior only.
EXPECTED_OUTPUT_TOKENS = {
    "extraction": 120, "summarization": 180, "classification": 20, "structured_json": 160,
    "reasoning": 250, "coding": 300, "data_interpretation": 220, "general": 250,
}

_KEYWORDS: dict[str, list[str]] = {
    "coding": [r"\bpython\b", r"\bfunction\b", r"\bdef \w+", r"\bimplement\b", r"\bcode\b", r"\balgorithm\b", r"\bregex\b", r"\bsql\b"],
    "structured_json": [r"\bjson\b", r"\bschema\b", r"\bkey[s]?\b.*\bvalue", r"\bfields?\b"],
    "extraction": [r"\bextract\b", r"\bpull out\b", r"\bidentify (all|the)\b", r"\blist (all|every)\b", r"\bfrom (the|this) (text|email|invoice|document)"],
    "summarization": [r"\bsummar", r"\btl;?dr\b", r"\bcondense\b", r"\bin (\d+|one|two|three) (sentences?|bullets?|words)\b"],
    "classification": [r"\bclassify\b", r"\bcategori[sz]e\b", r"\blabel\b", r"\bsentiment\b", r"\bwhich (category|class)\b", r"\bone of\b"],
    "reasoning": [r"\bhow many\b", r"\bcalculate\b", r"\bprove\b", r"\bdeduce\b", r"\bstep[- ]by[- ]step\b", r"\bif .* then\b", r"\bpuzzle\b", r"\bwhy\b"],
    "data_interpretation": [r"\btable\b", r"\bcsv\b", r"\bdataset\b", r"\baverage\b", r"\bmedian\b", r"\bgrowth\b", r"\btrend\b", r"\bpercent", r"\|.*\|"],
}

_REASONING_MARKERS = [r"\bstep[- ]by[- ]step\b", r"\bprove\b", r"\bderive\b", r"\bjustify\b", r"\bconstraint", r"\boptimi[sz]e\b", r"\bedge cases?\b", r"\bmulti-?step\b", r"\btrade-?offs?\b", r"\bcompare\b"]


@dataclass
class WorkloadAnalysis:
    category: str
    category_source: str  # "user" | "heuristic" | "router_model"
    complexity: float  # 0..1
    reasoning_required: bool
    code_generation: bool
    summarization: bool
    structured_output: bool
    input_tokens_est: int
    expected_output_tokens: int
    numeric_ops: int
    signals: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def infer_category(text: str) -> tuple[str, list[str]]:
    lower = text.lower()
    scores: dict[str, int] = {}
    hits: list[str] = []
    for cat, pats in _KEYWORDS.items():
        n = sum(1 for p in pats if re.search(p, lower))
        if n:
            scores[cat] = n
            hits.append(f"{cat} keywords ×{n}")
    if not scores:
        return "general", ["no category keywords matched"]
    # Precedence when tied: code and JSON constraints dominate the evaluation method.
    order = ["coding", "structured_json", "classification", "summarization", "extraction", "data_interpretation", "reasoning"]
    best = max(scores.items(), key=lambda kv: (kv[1], -order.index(kv[0])))[0]
    return best, hits


def analyze(task: str, category: str | None = None, output_format: str | None = None) -> WorkloadAnalysis:
    signals: list[str] = []
    if category and category in CATEGORIES:
        cat, source = category, "user"
        signals.append(f"category provided by caller: {category}")
    else:
        cat, hits = infer_category(task)
        source = "heuristic"
        signals.extend(hits)
        signals.append(f"inferred category: {cat}")

    lower = task.lower()
    words = len(task.split())
    input_tokens = max(1, round(len(task) / 4))
    reasoning_hits = [p for p in _REASONING_MARKERS if re.search(p, lower)]
    numeric_ops = len(re.findall(r"\d+(?:\.\d+)?", task))
    constraints = len(re.findall(r"\b(must|exactly|only|do not|don't|without|at least|at most|no more than)\b", lower))

    structured = output_format == "json" or cat == "structured_json" or "json" in lower
    code = cat == "coding"
    summarization = cat == "summarization"
    reasoning = cat in ("reasoning", "data_interpretation") or bool(reasoning_hits)

    # Complexity: additive, bounded, every term logged.
    complexity = 0.15
    terms = {
        "length": min(0.2, words / 1500),
        "reasoning markers": min(0.25, 0.08 * len(reasoning_hits)),
        "explicit constraints": min(0.15, 0.03 * constraints),
        "numeric content": min(0.15, 0.015 * numeric_ops) if cat in ("reasoning", "data_interpretation") else 0.0,
        "category base": {"reasoning": 0.2, "coding": 0.15, "data_interpretation": 0.12, "structured_json": 0.05}.get(cat, 0.0),
        "hard tag": 0.25 if "[hard]" in lower else 0.0,
    }
    for name, val in terms.items():
        if val > 0:
            complexity += val
            signals.append(f"+{val:.2f} complexity from {name}")
    complexity = round(min(1.0, complexity), 3)

    return WorkloadAnalysis(
        category=cat,
        category_source=source,
        complexity=complexity,
        reasoning_required=reasoning,
        code_generation=code,
        summarization=summarization,
        structured_output=structured,
        input_tokens_est=input_tokens,
        expected_output_tokens=EXPECTED_OUTPUT_TOKENS.get(cat, 250),
        numeric_ops=numeric_ops,
        signals=signals,
    )
