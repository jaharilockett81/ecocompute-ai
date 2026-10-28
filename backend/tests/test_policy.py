from app.router.analyzer import analyze
from app.router.policy import plan


def test_analyzer_infers_categories():
    assert analyze("Write a Python function that reverses a list").category == "coding"
    assert analyze("Classify the sentiment of this review as positive or negative").category == "classification"
    assert analyze("Summarize this memo in 3 bullets").category == "summarization"
    a = analyze("Explain step-by-step and prove the bound; consider edge cases and trade-offs", "reasoning")
    assert a.category_source == "user" and a.complexity > 0.5 and a.signals


def test_simple_and_complex_tasks_route_differently(settings):  # Acceptance test 2
    easy = analyze("Classify the sentiment: 'great product'. Reply with one label.", "classification")
    hard = analyze("Prove step-by-step, justify each constraint, compare trade-offs and edge cases, then optimize. " * 3, "reasoning")
    d_easy = plan(settings.tiers, easy, {}, quality_threshold=0.85)
    d_hard = plan(settings.tiers, hard, {}, quality_threshold=0.85, allow_escalation=False)
    assert d_easy.start_tier == "small"
    assert d_hard.start_tier != "small"
    assert d_easy.cost_units == "usd" and d_easy.options and d_easy.rationale


def test_evidence_moves_routing(settings):
    a = analyze("Extract the date from: meeting on 2026-01-02", "extraction")
    assert plan(settings.tiers, a, {}, quality_threshold=0.85).start_tier == "small"
    # Small tier observed failing 18/20 times on extraction: posterior collapses, router starts higher.
    ev = {("extraction", "small"): {"n": 20, "passes": 2}, ("extraction", "medium"): {"n": 20, "passes": 19}}
    d = plan(settings.tiers, a, ev, quality_threshold=0.85)
    assert d.start_tier == "medium"
    small = next(e for e in d.estimates if e.tier == "small")
    assert small.observed_n == 20 and small.pass_prob < 0.3


def test_forced_tier_and_escalation_chain(settings):
    a = analyze("anything", "general")
    d = plan(settings.tiers, a, {}, forced_tier="small", allow_escalation=True)
    assert d.forced and d.chain == ["small", "medium", "large"]
    d = plan(settings.tiers, a, {}, forced_tier="large", allow_escalation=False)
    assert d.chain == ["large"]


def test_infeasible_threshold_falls_back_to_best_probability(settings):
    a = analyze("hard", "reasoning")
    d = plan(settings.tiers, a, {}, quality_threshold=0.99, allow_escalation=False)
    assert d.start_tier == "large" and "No plan meets" in d.rationale


def test_exploration_is_bounded_and_labelled(settings):
    a = analyze("Prove step-by-step with edge cases", "reasoning")
    explored = [plan(settings.tiers, a, {}, quality_threshold=0.9, exploration_rate=1.0, seed=str(i)) for i in range(3)]
    assert all(d.explored and "Exploration" in d.rationale for d in explored if d.start_tier != plan(settings.tiers, a, {}, quality_threshold=0.9).start_tier)
