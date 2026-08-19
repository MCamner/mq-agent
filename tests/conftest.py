"""Test-wide isolation of the execution telemetry store.

Every emit point writes to `~/.mq-agent/execution-outcomes.jsonl` unless the
environment says otherwise, and several tests drive a real `SwarmRunner.run`.
Without this fixture each `pytest` run appends records to the operator's real
evidence store that look exactly like real runs. Learned routing is meant to
read that file, so test data indistinguishable from production data is not
untidiness — it is corrupted evidence.

Autouse, so an emit point added in a later phase is isolated by default rather
than by remembering to opt in.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_execution_outcomes(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "MQ_AGENT_EXECUTION_OUTCOMES", str(tmp_path / "execution-outcomes.jsonl")
    )
