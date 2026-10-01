from __future__ import annotations

import json
from pathlib import Path

import pytest
from git import Repo

from mq_agent.feedback import (
    read_comparison_history,
    read_experiment_history,
    run_context_experiment,
)
from mq_agent.feedback.engine import FeedbackExperimentError


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "mq-agent"
    root.mkdir()
    repo = Repo.init(root)
    with repo.config_writer() as config:
        config.set_value("user", "name", "Feedback Test")
        config.set_value("user", "email", "feedback-test@example.invalid")
    (root / "README.md").write_text("# test\n", encoding="utf-8")
    repo.index.add(["README.md"])
    repo.index.commit("baseline")
    return root


def _vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / ".mq").mkdir(parents=True)
    (root / ".mq" / "context-selection-vocabulary.json").write_text(
        json.dumps(
            {
                "source_heavy_hints": ["review"],
                "source_heavy_suppress": [],
                "max_codegraph_queries": 4,
            }
        ),
        encoding="utf-8",
    )
    cards = root / "memory" / "context-cards"
    cards.mkdir(parents=True)
    (cards / "mq-agent-card.md").write_text("# card\n", encoding="utf-8")
    return root


def _pack(*, codegraph: str, content: str | None = None) -> dict:
    body = content or ("active context\n" if codegraph == "off" else "shadow context\n")
    return {
        "content": body,
        "relevant_files": ["mq-agent/.mq/context/repo-card.md"],
        "cards": ["vault/memory/context-cards/mq-agent-card.md"],
        "card_metadata": {
            "mq-agent": {
                "freshness": "fresh",
                "scope": "public",
                "publishability": "public-safe",
            }
        },
    }


def test_f2_run_persists_measurements_but_not_raw_task(
    tmp_path, monkeypatch
) -> None:
    repo = _repo(tmp_path)
    vault = _vault(tmp_path)
    state = tmp_path / "state"
    secret_task = "review SECRET-TASK-BODY-DO-NOT-PERSIST"

    monkeypatch.setattr(
        "mq_agent.feedback.engine.build_task_pack",
        lambda *args, codegraph, **kwargs: _pack(codegraph=codegraph),
    )

    result = run_context_experiment(
        secret_task,
        repo,
        vault=vault,
        state_root=state,
    )

    assert result["status"] == "PASS"
    assert result["experiment"]["state"] == "completed"
    comparison = result["comparison"]
    assert comparison["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert comparison["metrics"]["context_tokens"]["status"] == "unavailable"
    assert comparison["metrics"]["external_api_calls"]["active"] == 0.0
    assert comparison["metrics"]["external_api_calls"]["shadow"] == 0.0
    assert len(read_experiment_history(state).records) == 1
    assert len(read_comparison_history(state).records) == 1
    persisted = (
        (state / "experiments.jsonl").read_text(encoding="utf-8")
        + (state / "comparisons.jsonl").read_text(encoding="utf-8")
    )
    assert secret_task not in persisted
    assert "SECRET-TASK-BODY" not in persisted


def test_f2_refuses_dirty_repo_before_collecting_context(tmp_path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    vault = _vault(tmp_path)
    (repo / "README.md").write_text("# dirty\n", encoding="utf-8")
    called = False

    def build(*args, **kwargs):
        nonlocal called
        called = True
        return _pack(codegraph="off")

    monkeypatch.setattr("mq_agent.feedback.engine.build_task_pack", build)

    with pytest.raises(FeedbackExperimentError, match="repo-worktree-dirty"):
        run_context_experiment("review repo", repo, vault=vault, state_root=tmp_path / "state")

    assert called is False


def test_f2_blocks_when_snapshot_drifts_between_active_and_shadow(
    tmp_path, monkeypatch
) -> None:
    repo_path = _repo(tmp_path)
    vault = _vault(tmp_path)
    state = tmp_path / "state"
    calls = 0

    def build(*args, codegraph, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            (repo_path / "README.md").write_text("# drift\n", encoding="utf-8")
        return _pack(codegraph=codegraph)

    monkeypatch.setattr("mq_agent.feedback.engine.build_task_pack", build)

    result = run_context_experiment(
        "review repo",
        repo_path,
        vault=vault,
        state_root=state,
    )

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "evidence-snapshot-drift"
    assert result["experiment"]["state"] == "blocked"
    assert read_comparison_history(state).records == []


def test_f2_shadow_context_budget_is_terminal_evidence(tmp_path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    vault = _vault(tmp_path)
    state = tmp_path / "state"

    def build(*args, codegraph, **kwargs):
        content = "ok\n" if codegraph == "off" else ("x" * 200)
        return _pack(codegraph=codegraph, content=content)

    monkeypatch.setattr("mq_agent.feedback.engine.build_task_pack", build)

    result = run_context_experiment(
        "review repo",
        repo,
        vault=vault,
        state_root=state,
        max_context_bytes=64,
    )

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "context-byte-budget-exceeded"
    assert result["experiment"]["state"] == "blocked"
    assert read_comparison_history(state).records == []


def test_f2_timeout_records_cancelled_without_comparison(tmp_path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    vault = _vault(tmp_path)
    state = tmp_path / "state"

    def timeout(*args, **kwargs):
        raise TimeoutError("feedback-context-timeout")

    monkeypatch.setattr("mq_agent.feedback.engine._collect_pack", timeout)

    result = run_context_experiment(
        "review repo",
        repo,
        vault=vault,
        state_root=state,
    )

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "feedback-context-timeout"
    assert result["experiment"]["state"] == "cancelled"
    assert read_comparison_history(state).records == []
