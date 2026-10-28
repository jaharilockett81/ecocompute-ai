"""Optional model-as-judge for subjective tasks with no deterministic check.

Scores are ESTIMATES. Known biases (self-preference, verbosity, position) are
mitigated, not removed: the judge model is configured separately from the
answering tiers where possible, uses a fixed rubric, sees no model identity,
and its cost is recorded as routing overhead.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.validators import parse_json_output
from app.providers.base import ChatResult

RUBRIC = """You are an impartial grader. Score the RESPONSE to the TASK on a 1-5 scale:
5 = fully correct, complete, follows every instruction and format constraint
4 = correct with minor omissions
3 = partially correct or misses an explicit instruction
2 = mostly incorrect or off-task
1 = wrong, empty, or refuses
Do not reward length. Ignore style unless the task asks for it.
Return ONLY JSON: {"score": <1-5 integer>, "rationale": "<one sentence>"}"""


@dataclass
class JudgeVerdict:
    score: float | None
    passed: bool | None
    rationale: str
    call: ChatResult


async def judge_output(provider, judge_model: str, task: str, response: str, pass_score: int = 4, max_tokens: int = 1024) -> JudgeVerdict:
    messages = [
        {"role": "system", "content": RUBRIC},
        {"role": "user", "content": f"TASK:\n{task}\n\nRESPONSE:\n{response}"},
    ]
    call = await provider.chat(judge_model, messages, max_tokens=max_tokens, temperature=0.0)
    if not call.ok:
        return JudgeVerdict(None, None, f"judge call failed: {call.error}", call)
    data, err = parse_json_output(call.content)
    if err or not isinstance(data, dict) or "score" not in data:
        return JudgeVerdict(None, None, f"judge returned unparseable verdict ({err or 'missing score'})", call)
    try:
        score = float(data["score"])
    except (TypeError, ValueError):
        return JudgeVerdict(None, None, "judge score not numeric", call)
    return JudgeVerdict(score, score >= pass_score, str(data.get("rationale", ""))[:300], call)
