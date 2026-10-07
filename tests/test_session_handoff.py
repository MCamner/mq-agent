from __future__ import annotations

import json
from pathlib import Path

import pytest

from mq_agent.memory.session_handoff import build_session_observation, handoff_session


def test_session_handoff_emits_typed_candidate_not_durable_memory(tmp_path: Path) -> None:
    payload = handoff_session(
        session_id="run-123",
        task_class="repo-repair",
        repository="MCamner/macos-scripts",
        outcome="self-check PASS",
        decisions=["interactive menu endings are lifecycle success"],
        artifact_refs=["commit:094d047"],
        corrections=["keep operational delegate failures non-zero"],
        confidence=0.9,
        vault=tmp_path,
    )

    assert payload["status"] == "SUBMITTED_FOR_REVIEW"
    assert payload["durable_memory_written"] is False
    inbox = tmp_path / "memory" / "observations" / "mq-agent.observations.jsonl"
    record = json.loads(inbox.read_text().splitlines()[0])
    assert record["schema"] == "memory-observation.v1"
    assert record["repository"] == "macos-scripts"
    assert record["workflow"] == "session-handoff"
    assert record["evidence"][0]["reference"] == "commit:094d047"


def test_session_handoff_rejects_private_paths_and_credentials() -> None:
    with pytest.raises(ValueError, match="private absolute path"):
        build_session_observation(
            session_id="run-1",
            task_class="repo-repair",
            repository="mq-agent",
            outcome="PASS",
            decisions=["read /Users/private/secret.txt"],
        )

    with pytest.raises(ValueError, match="credential-like"):
        build_session_observation(
            session_id="run-1",
            task_class="repo-repair",
            repository="mq-agent",
            outcome="PASS",
            corrections=["token sk-abcdefghijklmnopqrstuvwxyz"],
        )
