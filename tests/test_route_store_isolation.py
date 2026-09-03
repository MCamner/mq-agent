"""Tests must not be able to write to the real evidence stores.

This was a convention until now — set `MQ_AGENT_ROUTE_OUTCOMES` and remember to
keep setting it. It was broken once in practice, and because routing history is
never deleted or backfilled, the stray record could only be excluded by era,
not removed. A convention that cannot be undone when broken should be a
mechanism.
"""
from __future__ import annotations

import os
from pathlib import Path

from mq_agent.tools.execution_outcome import outcome_path as execution_outcome_path
from mq_agent.tools.model_routing import _outcome_path


def test_the_store_used_by_tests_is_not_the_real_one() -> None:
    assert _outcome_path() != Path.home() / ".mq-agent/route-outcomes.jsonl"


def test_the_redirection_is_what_the_code_actually_reads() -> None:
    # Asserting the environment variable alone would prove nothing about where
    # a recorded outcome lands.
    assert str(_outcome_path()) == os.environ["MQ_AGENT_ROUTE_OUTCOMES"]


def test_an_explicit_destination_still_wins() -> None:
    # The isolation must not break a caller that names its own store.
    assert _outcome_path(Path("/tmp/elsewhere.jsonl")) == Path("/tmp/elsewhere.jsonl")


def test_the_execution_store_is_redirected_too() -> None:
    """It needed it more than the routing store did.

    `test_the_suite_never_writes_to_the_operators_real_store` passed in a full
    run and failed on its own: it was satisfied by an environment variable
    another test happened to leave behind. The claim is now true in every
    invocation, for a reason rather than by ordering.
    """
    assert execution_outcome_path() != Path.home() / ".mq-agent/execution-outcomes.jsonl"
    assert str(execution_outcome_path()) == os.environ["MQ_AGENT_EXECUTION_OUTCOMES"]
