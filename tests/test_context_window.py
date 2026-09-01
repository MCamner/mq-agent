"""A context window that does not fit must fail loudly.

The defect these tests exist to prevent, measured on 2026-09-01: a ~19,000 token
prompt sent with no `num_ctx`, Ollama's 4096-token default silently applied,
`prompt_eval_count` 4098, and a normal-looking candidate whose citations were
then checked against material the model had never seen.

Nothing raised. Nothing was recorded. The evidence chain reported model quality
for a run where the model and the verifier read different documents.
"""
from __future__ import annotations

import pytest

from mq_agent.tools import model_routing
from mq_agent.tools.context_window import (
    DEFAULT_MAX_CONTEXT_TOKENS,
    RESPONSE_BUDGET_TOKENS,
    configured_limit,
    estimate_tokens,
    plan_context,
    was_truncated,
)


def test_the_estimate_is_deliberately_high_for_this_material() -> None:
    # Measured chars/token against prompt_eval_count on what this system sends:
    # README prose 3.76, audit material 2.86 and 2.99. The constant sits below
    # every one of them, so the estimate errs toward refusing rather than
    # truncating. "4 chars per token" is prose folklore and underestimates repo
    # paths, diffs and log lines by about a third — in exactly the direction
    # that turns a preflight into a truncation.
    assert estimate_tokens("x" * 1000) >= 1000 / 2.86


def test_a_small_prompt_does_not_reserve_the_whole_ceiling() -> None:
    # Sizing to the request, not to the limit: a 3 KB prompt has no business
    # allocating 32k of KV cache.
    plan = plan_context("x" * 3000, 262144)

    assert plan.fits
    assert plan.num_ctx < DEFAULT_MAX_CONTEXT_TOKENS


def test_the_window_leaves_room_to_answer_in() -> None:
    # A prompt that fills the window leaves nothing to respond with.
    prompt = "x" * 3000
    plan = plan_context(prompt, 262144)

    assert plan.required_tokens >= plan.estimated_prompt_tokens + RESPONSE_BUDGET_TOKENS


def test_todays_docs_audit_material_does_not_fit_the_ceiling() -> None:
    # The honest consequence of the locked policy, asserted rather than
    # discovered later: 75,935 characters of docs-audit material needs ~38k
    # tokens with the response budget and margin, against a 32,768 ceiling. It
    # is refused, not run. That is what makes context selection necessary rather
    # than optional — and it is why the old behaviour looked like it worked.
    plan = plan_context("x" * 75935, 262144)

    assert not plan.fits
    assert plan.required_tokens > DEFAULT_MAX_CONTEXT_TOKENS


def test_the_operator_ceiling_caps_a_capable_model(monkeypatch) -> None:
    monkeypatch.setenv("MQ_AGENT_MAX_CONTEXT_TOKENS", "8192")

    plan = plan_context("x" * 3000, 262144)

    assert plan.effective_limit == 8192


def test_a_small_model_caps_a_generous_operator(monkeypatch) -> None:
    # min(policy, capability). The operator may want more than the model has.
    monkeypatch.setenv("MQ_AGENT_MAX_CONTEXT_TOKENS", "32768")

    plan = plan_context("x" * 3000, 4096)

    assert plan.effective_limit == 4096


def test_an_unreadable_model_limit_does_not_become_unlimited() -> None:
    # None means unknown, never unlimited. Assuming capability is how the silent
    # truncation stayed invisible.
    plan = plan_context("x" * 3000, None)

    assert plan.effective_limit == configured_limit()


@pytest.mark.parametrize("value", ["", "nonsense", "0", "-5"])
def test_an_unusable_ceiling_setting_falls_back_to_the_default(value, monkeypatch) -> None:
    monkeypatch.setenv("MQ_AGENT_MAX_CONTEXT_TOKENS", value)

    assert configured_limit() == DEFAULT_MAX_CONTEXT_TOKENS


def test_a_saturated_window_is_a_truncated_prompt() -> None:
    # The original defect's own numbers: a 4096-token window reporting 4098.
    assert was_truncated(4098, 4096)


def test_a_window_with_room_left_was_not_truncated() -> None:
    assert not was_truncated(941, 6144)


def test_an_absent_count_is_not_claimed_as_truncation() -> None:
    # Ollama omits the count for a fully cached prompt. Unknown is not the same
    # as truncated, and this check must not invent the observation it exists to
    # make. The preflight is the primary guarantee for exactly this reason.
    assert not was_truncated(None, 4096)
    assert not was_truncated(0, 4096)


def _decision_patch(monkeypatch, *, limit: int | None = 262144) -> dict:
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(model_routing, "model_context_limit", lambda *_a, **_k: limit)
    calls: dict = {}

    def _generate(model, prompt, timeout, **kwargs):
        calls["num_ctx"] = kwargs.get("num_ctx")
        calls["prompt_chars"] = len(prompt)
        return {
            "response": '{"task_class": "diff-summary", "summary": "s", '
            '"evidence": [], "suggestions": []}',
            "prompt_eval_count": kwargs.get("num_ctx", 0) // 2,
        }

    monkeypatch.setattr(model_routing, "_ollama_generate", _generate)
    return calls


def test_an_oversized_prompt_is_refused_before_inference(monkeypatch) -> None:
    calls = _decision_patch(monkeypatch)

    result = model_routing.shadow_route("Summarize this diff", context="x" * 200000)
    outcome = result["outcome"]

    assert outcome["escalation_reason"] == "context-window-exceeded"
    assert outcome["verification"]["status"] == "FAIL"
    # The model was never called. Not "it failed" — it did not run.
    assert outcome["attempted"] is False
    assert "num_ctx" not in calls


def test_the_request_carries_an_explicit_window(monkeypatch) -> None:
    # The whole defect in one assertion: without this the backend silently
    # applies its own default.
    calls = _decision_patch(monkeypatch)

    model_routing.shadow_route("Summarize this diff", context="x" * 2000)

    assert calls["num_ctx"] is not None
    assert calls["num_ctx"] >= 2048


def test_a_truncated_prompt_never_passes(monkeypatch) -> None:
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(model_routing, "model_context_limit", lambda *_a, **_k: 262144)

    def _saturated(model, prompt, timeout, **kwargs):
        return {
            "response": '{"task_class": "diff-summary", "summary": "s", '
            '"evidence": [], "suggestions": []}',
            # The backend filled the window it was given.
            "prompt_eval_count": kwargs["num_ctx"],
        }

    monkeypatch.setattr(model_routing, "_ollama_generate", _saturated)

    result = model_routing.shadow_route("Summarize this diff", context="x" * 2000)
    outcome = result["outcome"]

    assert result["candidate"] is None
    assert outcome["escalation_reason"] == "context-truncated"
    assert outcome["verification"]["status"] == "FAIL"
    # It ran, and what came back cannot be trusted. Both facts are recorded.
    assert outcome["attempted"] is True
    assert outcome["model_output_received"] is True


def test_a_context_fault_is_not_reported_as_model_unavailability(monkeypatch) -> None:
    # The model answered. The material did not fit. Recording
    # `model-unavailable` would send someone to debug the wrong thing, and
    # `verification-failed` would claim the model saw the material and cited it
    # wrongly — the one thing that is certainly untrue here.
    _decision_patch(monkeypatch)

    outcome = model_routing.shadow_route(
        "Summarize this diff", context="x" * 200000
    )["outcome"]

    assert outcome["escalation_reason"] not in {"model-unavailable", "verification-failed"}


def test_both_context_reasons_validate_against_the_contract(monkeypatch) -> None:
    validator = model_routing._validator("model_route_outcome.schema.json")
    _decision_patch(monkeypatch)

    outcome = model_routing.shadow_route(
        "Summarize this diff", context="x" * 200000
    )["outcome"]

    validator.validate(outcome)
