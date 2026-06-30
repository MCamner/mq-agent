"""Co-change memory-observation emission tests (CG-2).

mq-agent is the producer that turns Bridget/CG-2 co-change evidence into one
sanitized ``memory-observation.v1`` proposal. These lock the record shape against
mqobsidian's schema (required fields, known keys only, evidence provenance), the
gate (weak/empty signal emits nothing), public-safety (basename repo), and
best-effort emission. No real Bridget, no network — the runner is faked.
"""
from __future__ import annotations

import json

from mq_agent.memory.cochange_observation import (
    EVIDENCE_SOURCE,
    PRODUCER,
    SCHEMA_ID,
    build_observation,
    emit_cochange,
    emit_observation,
    observations_inbox,
)

# Top-level keys allowed by mqobsidian schemas/memory-observation.v1.json
# (additionalProperties:false). The record must use only these.
_ALLOWED_KEYS = {
    "schema", "id", "timestamp", "producer", "repository", "workflow",
    "session_id", "title", "summary", "observation", "category", "confidence",
    "evidence", "tags", "related", "proposed_memory_key", "metadata",
}
_REQUIRED_KEYS = {
    "schema", "id", "timestamp", "producer", "repository", "title",
    "observation", "category", "confidence", "evidence",
}


def _cochange_json(rows=None, *, repo="mq-mcp", run_id="cochange-run-20260629T010203Z-deadbeef"):
    return {
        "run_id": run_id,
        "repo": repo,
        "target": "mq-mcp/bridge.py",
        "window": 300,
        "generated_at": "2026-06-29T01:02:03+00:00",
        "rows": rows if rows is not None else [
            {"path": "mq-mcp/bridget_context.py", "count": 4, "base": 5, "confidence": 0.8},
            {"path": "mq-mcp/server.py", "count": 3, "base": 5, "confidence": 0.6},
        ],
    }


# --- build_observation ------------------------------------------------------


def test_build_observation_valid_record():
    rec = build_observation(_cochange_json(), "mq-mcp/bridge.py")
    assert rec is not None
    assert _REQUIRED_KEYS <= set(rec)
    assert set(rec) <= _ALLOWED_KEYS  # known keys only
    assert rec["schema"] == SCHEMA_ID
    assert rec["producer"] == PRODUCER
    assert 0.0 <= rec["confidence"] <= 1.0
    assert rec["category"] in {"pattern", "architecture"}
    # provenance: Bridget is the evidence source, run_id is the reference
    ev = rec["evidence"][0]
    assert ev["source"] == EVIDENCE_SOURCE
    assert ev["reference"] == "cochange-run-20260629T010203Z-deadbeef"
    # the strong co-changer appears in the human observation
    assert "bridget_context.py" in rec["observation"]


def test_build_observation_repository_is_basename():
    rec = build_observation(_cochange_json(repo="/Users/x/mq-mcp"), "mq-mcp/bridge.py")
    assert rec is not None
    assert rec["repository"] == "mq-mcp"  # never an absolute path


def test_build_observation_uses_repo_relative_target_from_evidence():
    # Even when the caller passes an ABSOLUTE path (run_cochange does this so
    # Bridget resolves the right repo), the stored record uses Bridget's
    # repo-relative `target` — no absolute path leaks into text or keys.
    rec = build_observation(_cochange_json(), "/Users/x/repos/mq-mcp/mq-mcp/bridge.py")
    assert rec is not None
    assert "/Users/x/" not in rec["observation"]
    assert "/Users/x/" not in rec["proposed_memory_key"]
    assert "/Users/x/" not in rec["id"]
    assert rec["proposed_memory_key"] == "cochange-mq-mcp-bridge-py"
    assert "mq-mcp/bridge.py" in rec["observation"]


def test_build_observation_empty_rows_returns_none():
    assert build_observation(_cochange_json(rows=[]), "mq-mcp/bridge.py") is None


def test_build_observation_below_gate_returns_none():
    # meets support (count>=2) but confidence under the default 0.05 gate
    weak = [{"path": "x.py", "count": 2, "base": 100, "confidence": 0.02}]
    assert build_observation(_cochange_json(rows=weak), "mq-mcp/bridge.py") is None


def test_build_observation_confidence_clamped():
    hot = [{"path": "y.py", "count": 6, "base": 5, "confidence": 1.2}]
    rec = build_observation(_cochange_json(rows=hot), "mq-mcp/bridge.py")
    assert rec is not None and rec["confidence"] == 1.0


# --- emit -------------------------------------------------------------------


def test_emit_cochange_writes_one_line(tmp_path):
    def fake_runner(repo, target, *, window, mq_mcp_dir=None):
        return _cochange_json()

    path = emit_cochange("/repos/mq-mcp", "mq-mcp/bridge.py", runner=fake_runner, vault=tmp_path)
    assert path == observations_inbox(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["schema"] == SCHEMA_ID and rec["producer"] == PRODUCER


def test_emit_cochange_no_evidence_writes_nothing(tmp_path):
    def empty_runner(repo, target, *, window, mq_mcp_dir=None):
        return None

    assert emit_cochange("/r", "f.py", runner=empty_runner, vault=tmp_path) is None
    assert not observations_inbox(tmp_path).exists()


def test_emit_cochange_below_gate_writes_nothing(tmp_path):
    def weak_runner(repo, target, *, window, mq_mcp_dir=None):
        return _cochange_json(rows=[{"path": "x.py", "count": 2, "base": 100, "confidence": 0.02}])

    assert emit_cochange("/r", "f.py", runner=weak_runner, vault=tmp_path) is None
    assert not observations_inbox(tmp_path).exists()


def test_run_cochange_passes_absolute_target(monkeypatch):
    # The --co-change argument must be an absolute path (repo/target), so Bridget
    # resolves the analyzed repo correctly despite `uv --directory` forcing cwd to
    # the mq-mcp project. A relative target would silently analyze the wrong repo.
    from mq_agent.memory import cochange_observation as co

    captured: dict = {}

    class _Result:
        returncode = 0
        stdout = json.dumps({"repo": "macos-scripts", "target": "terminal/menu.sh", "rows": []})

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(co.subprocess, "run", fake_run)
    co.run_cochange("/repos/macos-scripts", "terminal/menu.sh", mq_mcp_dir="/m")
    cmd = captured["cmd"]
    target_arg = cmd[cmd.index("--co-change") + 1]
    assert target_arg == "/repos/macos-scripts/terminal/menu.sh"


def test_emit_observation_best_effort_on_bad_vault(tmp_path):
    # vault path is a FILE, so mkdir of the inbox dir fails — must not raise.
    bad = tmp_path / "not-a-dir"
    bad.write_text("x", encoding="utf-8")
    rec = build_observation(_cochange_json(), "mq-mcp/bridge.py")
    assert emit_observation(rec, vault=bad) is None
