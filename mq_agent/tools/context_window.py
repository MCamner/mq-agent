"""Make a context window that does not fit an explicit failure, not a silent one.

Measured on 2026-09-01: `_ollama_generate` never sent `options.num_ctx`, so
Ollama applied its 4096-token default to a ~19,000 token prompt and processed
4098 of them. No error. A normal-looking candidate came back, and the verifier
then checked its citations against the *full* material — material the model had
never seen.

    prompt chars       75935
    prompt_eval_count   4098

That is an integrity fault in the evidence chain, not a quality result. The
invariant this module restores:

    the model is given the material the verifier later checks against,
    or the execution says so explicitly

Two failures, separated by when they are found. `context-window-exceeded` is a
refusal before inference. `context-truncated` is discovered afterwards, from the
backend's own count. Preflight is the primary guarantee; the postflight check
exists because preflight rests on an estimate and the backend's count does not.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

#: Operational ceiling, not a model capability. `qwen3:4b-instruct` advertises
#: 262144, but allocating a window costs memory and prompt processing scales
#: with it, so how much context this system is willing to spend is a runtime
#: policy the operator sets — never a number read off the model.
DEFAULT_MAX_CONTEXT_TOKENS = 32768

#: Room the response needs inside the same window. A prompt that fills the
#: window leaves nothing to answer with.
RESPONSE_BUDGET_TOKENS = 4096

#: Applied on top of prompt + response, for chat template and format-grammar
#: overhead this module cannot see.
SAFETY_MARGIN = 0.10

#: Deliberately below every ratio measured, so estimates come out high and the
#: preflight refuses rather than truncates. Measured against `prompt_eval_count`
#: on the material this system actually sends:
#:
#:     README prose        3.76 chars/token
#:     audit material 8k   2.86
#:     audit material 20k  2.99
#:
#: The familiar "4 chars per token" is prose folklore; on repo paths, diffs and
#: log lines it underestimates by about a third, which is exactly the direction
#: that turns a preflight into a truncation.
_CHARS_PER_TOKEN = 2.5

#: Windows are requested in whole steps. Smaller than this is not worth asking
#: for and risks refusing a trivial prompt over rounding.
_NUM_CTX_STEP = 1024
_MIN_NUM_CTX = 2048


@dataclass(frozen=True)
class ContextPlan:
    """What window this request needs, and whether it may have it."""

    estimated_prompt_tokens: int
    required_tokens: int
    effective_limit: int
    num_ctx: int
    fits: bool


def estimate_tokens(text: str) -> int:
    """A deliberately high estimate of how many tokens `text` will become.

    An estimate, not a measurement — there is no tokenizer here and Ollama
    exposes no tokenize endpoint. The only exact number is `prompt_eval_count`,
    which arrives after the call, which is why `was_truncated` exists.
    """
    return math.ceil(len(text) / _CHARS_PER_TOKEN)


def configured_limit() -> int:
    """The operator's ceiling. Invalid or absent settings fall back to the default."""
    raw = os.environ.get("MQ_AGENT_MAX_CONTEXT_TOKENS", "").strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_CONTEXT_TOKENS
    return value if value > 0 else DEFAULT_MAX_CONTEXT_TOKENS


def plan_context(prompt: str, model_limit: int | None = None) -> ContextPlan:
    """Size the window to this request, and say whether the request is allowed.

    `model_limit` is the model's declared maximum when it could be read. When it
    could not, the operator's ceiling stands alone: assuming the model will take
    anything would be inventing a number, which is the habit this whole change
    exists to break.

    The window is sized to what the request needs rather than set to the
    ceiling. A 3 KB prompt should not reserve 32k of KV cache.
    """
    limit = configured_limit()
    effective_limit = min(limit, model_limit) if model_limit else limit

    estimated = estimate_tokens(prompt)
    required = math.ceil((estimated + RESPONSE_BUDGET_TOKENS) * (1 + SAFETY_MARGIN))

    num_ctx = max(_MIN_NUM_CTX, math.ceil(required / _NUM_CTX_STEP) * _NUM_CTX_STEP)
    fits = required <= effective_limit
    return ContextPlan(
        estimated_prompt_tokens=estimated,
        required_tokens=required,
        effective_limit=effective_limit,
        num_ctx=min(num_ctx, effective_limit),
        fits=fits,
    )


def was_truncated(prompt_eval_count: int | None, num_ctx: int) -> bool:
    """Did the backend fill the window it was given?

    Saturation is the reliable signal, and it is the one the original defect
    left behind: a 4096-token window reported `prompt_eval_count` 4098. Comparing
    against the character estimate instead would inherit the estimate's error.

    An absent or zero count means the check could not run — Ollama omits it for a
    fully cached prompt — and this returns False rather than claiming a
    truncation it did not observe. That gap is why the preflight is the primary
    guarantee and this is the second line.
    """
    if not prompt_eval_count:
        return False
    return prompt_eval_count >= num_ctx
