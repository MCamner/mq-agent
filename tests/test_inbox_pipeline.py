"""Operator-triggered co-change inbox pipeline — orchestration tests.

No real Bridget, no real mqobsidian CLI: both seams are injected. We assert the
stack boundary holds (mq-agent orchestrates, delegates scoring/writeback to
mqobsidian), that --dry-run/--no-writeback behave, and that the emitted record keeps
producer=mq-agent + evidence.source=bridget/cg-2.
"""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.memory import inbox_pipeline as ip

runner = CliRunner()

_STRONG = {
    "repo": "macos-scripts",
    "run_id": "cochange-run-20260629T000000Z-abc12345",
    "target": "terminal/mqlaunch.sh",
    "window": 300,
    "rows": [
        {"path": "terminal/foo.sh", "confidence": 0.6, "count": 6, "base": 10},
        {"path": "terminal/bar.sh", "confidence": 0.3, "count": 3, "base": 10},
    ],
}
_WEAK = {"repo": "macos-scripts", "run_id": "r", "target": "x", "window": 300,
         "rows": [{"path": "y", "confidence": 0.6, "count": 1, "base": 10}]}  # count < min_support


def _runner(data):
    def fake(repo, target, *, window=300, mq_mcp_dir=None):
        return data
    return fake


class _RecordingCLI:
    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, vault: Path, args: list[str]):
        self.calls.append(args)
        return 0, f"{args[0]} summary", ""


# --- happy path ------------------------------------------------------------

def test_emit_happy_path_writes_inbox_and_delegates(tmp_path):
    cli = _RecordingCLI()
    res = ip.run_pipeline(
        "repo", "terminal/mqlaunch.sh", vault=tmp_path,
        runner=_runner(_STRONG), cli_runner=cli,
    )
    assert res["evidence"]["found"] and res["evidence"]["run_id"] == "cochange-run-20260629T000000Z-abc12345"
    assert res["emit"]["status"] == "emitted"
    inbox = tmp_path / "memory" / "observations" / "mq-agent.observations.jsonl"
    assert inbox.exists()
    rec = json.loads(inbox.read_text().strip())
    assert rec["producer"] == "mq-agent"
    assert rec["evidence"][0]["source"] == "bridget/cg-2"
    # mq-agent delegated scoring/writeback/status to mqobsidian's CLI — in order.
    assert cli.calls == [["score", "--apply"], ["learn-writeback", "--apply"], ["status"]]
    assert res["ok"] is True


def test_dry_run_writes_nothing(tmp_path):
    cli = _RecordingCLI()
    res = ip.run_pipeline(
        "repo", "terminal/mqlaunch.sh", vault=tmp_path, dry_run=True,
        runner=_runner(_STRONG), cli_runner=cli,
    )
    assert res["emit"]["status"] == "would-emit"
    assert not (tmp_path / "memory" / "observations" / "mq-agent.observations.jsonl").exists()
    assert cli.calls == [["score", "--dry-run"], ["learn-writeback", "--dry-run"], ["status"]]


def test_no_writeback_scores_but_skips_writeback(tmp_path):
    cli = _RecordingCLI()
    res = ip.run_pipeline(
        "repo", "terminal/mqlaunch.sh", vault=tmp_path, no_writeback=True,
        runner=_runner(_STRONG), cli_runner=cli,
    )
    assert res["writeback"].get("skipped") == "--no-writeback"
    assert ["learn-writeback", "--apply"] not in cli.calls
    assert cli.calls == [["score", "--apply"], ["status"]]


def test_no_cluster_skips_emit_but_still_scores(tmp_path):
    cli = _RecordingCLI()
    res = ip.run_pipeline("repo", "x", vault=tmp_path, runner=_runner(_WEAK), cli_runner=cli)
    assert res["emit"]["status"] == "skipped"
    assert not (tmp_path / "memory" / "observations" / "mq-agent.observations.jsonl").exists()
    assert cli.calls[0] == ["score", "--apply"]  # scoring still runs after emission


def test_unavailable_evidence_is_graceful(tmp_path):
    cli = _RecordingCLI()
    res = ip.run_pipeline("repo", "x", vault=tmp_path, runner=_runner(None), cli_runner=cli)
    assert res["evidence"]["found"] is False
    assert res["emit"]["status"] == "skipped" and "unavailable" in res["emit"]["detail"]


# --- vault resolution ------------------------------------------------------

def test_vault_resolution_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ_OBSIDIAN_DIR", str(tmp_path / "fromenv"))
    assert ip.resolve_vault("/explicit") == Path("/explicit")          # flag wins
    assert ip.resolve_vault(None) == tmp_path / "fromenv"              # then env
    monkeypatch.delenv("MQ_OBSIDIAN_DIR")
    assert ip.resolve_vault(None).name == "mqobsidian"                 # then default


def test_missing_mqobsidian_cli_is_reported_not_raised(tmp_path):
    rc, out, err = ip.run_mqobsidian_cli(tmp_path, ["status"])
    assert rc == 127 and "not found" in err


# --- CLI wiring (graceful with no real deps) -------------------------------

def test_cli_command_wires_and_degrades_gracefully(tmp_path):
    # No Bridget + tmp vault has no memory_cli.py → every stage degrades, no crash.
    result = runner.invoke(app, ["memory", "inbox-cochange", str(tmp_path), "f.py", "--vault", str(tmp_path)])
    assert "MQ memory co-change intake" in result.output
    assert "Bridget/CG-2 evidence" in result.output
    assert "mqobsidian scoring" in result.output


# --- review / resolution surface (explicit mqobsidian delegators) ----------

def test_review_status_delegates_status(tmp_path):
    cli = _RecordingCLI()
    res = ip.run_review_status(vault=tmp_path, cli_runner=cli)
    assert cli.calls == [["status"]] and res["ok"] is True


def test_promote_from_review_dry_run_by_default(tmp_path):
    cli = _RecordingCLI()
    ip.run_promote_from_review("cochange-x", vault=tmp_path, cli_runner=cli)
    assert cli.calls == [["promote-from-review", "cochange-x"]]  # no --apply


def test_promote_from_review_apply_passes_flag(tmp_path):
    cli = _RecordingCLI()
    ip.run_promote_from_review("cochange-x", apply=True, vault=tmp_path, cli_runner=cli)
    assert cli.calls == [["promote-from-review", "cochange-x", "--apply"]]


def test_resolve_supersede_accept_and_reject(tmp_path):
    cli = _RecordingCLI()
    ip.run_resolve_supersede("gen-x", accept=True, apply=True, vault=tmp_path, cli_runner=cli)
    ip.run_resolve_supersede("gen-x", accept=False, vault=tmp_path, cli_runner=cli)
    assert cli.calls == [
        ["resolve-supersede", "gen-x", "--accept", "--apply"],
        ["resolve-supersede", "gen-x", "--reject"],
    ]


def test_resolve_supersede_requires_exactly_one_mode(tmp_path):
    # Neither --accept nor --reject → exit 2, no delegation.
    result = runner.invoke(app, ["memory", "resolve-supersede", "gen-x", "--vault", str(tmp_path)])
    assert result.exit_code == 2 and "exactly one of --accept or --reject" in result.output


def test_review_cli_commands_degrade_gracefully(tmp_path):
    # tmp vault has no memory_cli.py → reported as failed rc=127, no crash.
    r = runner.invoke(app, ["memory", "review-status", "--vault", str(tmp_path)])
    assert "MQ memory review status" in r.output and "failed rc=127" in r.output


# --- deterministic ranking (v1.22 Task 7) -----------------------------------
#
# The formula and the routing are mq-agent code; the weights and thresholds are
# mqobsidian data. These tests therefore never hardcode a threshold — they pass
# a policy in and assert the routing that policy implies.

_FACTORS = ("frequency", "source_count", "confidence", "recency", "usage_score", "manual_boost")


def _policy(**over) -> dict:
    policy = {
        "schema": "promotion-policy.v1", "source": "mqobsidian-export",
        "generated_at": "2026-07-16T00:00:00Z",
        "weights": {f: 1.0 for f in _FACTORS},
        "review_threshold": 1.0, "auto_threshold": 3.0, "min_supporting_factors": 2,
        "block_negative_feedback": True, "max_manifest_age_seconds": 86400,
    }
    policy.update(over)
    return policy


def _exports(items, scores, evidence, policy=None) -> dict:
    return {
        "inbox": {"schema": "inbox-manifest.v1", "source": "mqobsidian-export",
                  "generated_at": "2026-07-16T00:00:00Z", "items": items},
        "scores": {"schema": "memory-score-manifest.v1", "source": "mqobsidian-export",
                   "generated_at": "2026-07-16T00:00:00Z", "scores": scores},
        "evidence": {"schema": "memory-evidence-manifest.v1", "source": "mqobsidian-export",
                     "generated_at": "2026-07-16T00:00:00Z", "evidence": evidence},
        "promotion-policy": policy or _policy(),
    }


def _item(**over) -> dict:
    item = {"id": "m-1", "source": "repo-signal", "state": "candidate",
            "first_seen": "2026-07-01T00:00:00Z", "last_seen": "2026-07-15T00:00:00Z",
            "evidence": [{"ref": "observation:o1", "kind": "observation"}]}
    item.update(over)
    return item


def _score(**over) -> dict:
    score = {"schema": "memory-score.v1", "memory_id": "m-1", "timestamp": "2026-07-16T00:00:00Z",
             "status": "candidate", "score": 0.5,
             "factors": {f: 1.0 for f in _FACTORS},
             "feedback": {"positive": 1, "negative": 0}}
    score.update(over)
    return score


def _ev(ref="observation:o1", candidate="m-1", producer="repo-signal") -> dict:
    return {"ref": ref, "producer": producer, "schema_id": "memory-observation.v1",
            "candidate_id": candidate, "kind": "observation",
            "observed_at": "2026-07-15T00:00:00Z", "summary": "a pattern"}


def _one(exports) -> dict:
    ranking = ip.build_ranking(exports)
    assert len(ranking["candidates"]) == 1
    return ranking["candidates"][0]


def test_ranked_score_is_the_policy_weighted_sum_of_factors():
    policy = _policy(weights={"frequency": 0.5, "source_count": 0.25, "confidence": 2.0,
                              "recency": 0.0, "usage_score": 0.0, "manual_boost": 0.0})
    factors = {"frequency": 2.0, "source_count": 4.0, "confidence": 0.5,
               "recency": 9.0, "usage_score": 9.0, "manual_boost": 9.0}
    got = _one(_exports([_item()], {"m-1": _score(factors=factors)},
                        {"observation:o1": _ev()}, policy))
    # 0.5*2 + 0.25*4 + 2.0*0.5 + zero-weighted terms = 3.0
    assert got["ranked_score"] == 3.0
    assert got["contributions"]["confidence"] == 1.0
    assert got["contributions"]["recency"] == 0.0, "a zero weight must contribute nothing"


def test_weights_come_from_policy_not_from_mq_agent():
    """Same factors, different owner policy → different result. No hardcoding."""
    factors = {f: 1.0 for f in _FACTORS}
    low = _one(_exports([_item()], {"m-1": _score(factors=factors)}, {"observation:o1": _ev()},
                        _policy(weights={f: 0.1 for f in _FACTORS})))
    high = _one(_exports([_item()], {"m-1": _score(factors=factors)}, {"observation:o1": _ev()},
                         _policy(weights={f: 10.0 for f in _FACTORS})))
    assert low["ranked_score"] == 0.6 and high["ranked_score"] == 60.0


def test_buckets_follow_the_owner_thresholds():
    cases = [(0.0, "inbox"), (1.0, "review-needed"), (2.9, "review-needed"), (3.0, "auto-promotable")]
    for target, expected in cases:
        # one factor carries the whole score; the rest are zero-weighted
        factors = {f: (target if f == "confidence" else 0.0) for f in _FACTORS}
        policy = _policy(weights={f: (1.0 if f == "confidence" else 0.0) for f in _FACTORS},
                         min_supporting_factors=1)
        got = _one(_exports([_item()], {"m-1": _score(factors=factors)},
                            {"observation:o1": _ev()}, policy))
        assert got["bucket"] == expected, f"{target} should bucket as {expected}"


def test_missing_evidence_is_never_auto_promotable():
    got = _one(_exports([_item(evidence=[])], {"m-1": _score()}, {}))
    assert got["bucket"] == "review-needed"
    assert "missing-evidence" in got["review_reasons"]


def test_unresolved_evidence_ref_is_never_auto_promotable():
    got = _one(_exports([_item()], {"m-1": _score()}, {}))  # ref not in the manifest
    assert got["bucket"] == "review-needed"
    assert "unresolved-evidence" in got["review_reasons"]
    assert got["provenance"] == [], "an unresolved ref must not become provenance"


def test_conflicting_evidence_is_never_auto_promotable():
    """Evidence that claims to support a different candidate is a contradiction."""
    got = _one(_exports([_item()], {"m-1": _score()},
                        {"observation:o1": _ev(candidate="someone-else")}))
    assert got["bucket"] == "review-needed"
    assert "conflicting-evidence" in got["review_reasons"]


def test_single_factor_support_is_never_auto_promotable():
    factors = {f: (5.0 if f == "confidence" else 0.0) for f in _FACTORS}
    got = _one(_exports([_item()], {"m-1": _score(factors=factors)}, {"observation:o1": _ev()}))
    assert got["supporting_factors"] == 1
    assert got["bucket"] == "review-needed"
    assert "insufficient-supporting-factors" in got["review_reasons"]


def test_negative_feedback_is_never_auto_promotable_when_policy_blocks():
    score = _score(feedback={"positive": 0, "negative": 1}, factors={f: 5.0 for f in _FACTORS})
    got = _one(_exports([_item()], {"m-1": score}, {"observation:o1": _ev()}))
    assert got["bucket"] == "review-needed"
    assert "negative-feedback" in got["review_reasons"]

    allowed = _one(_exports([_item()], {"m-1": score}, {"observation:o1": _ev()},
                            _policy(block_negative_feedback=False)))
    assert allowed["bucket"] == "auto-promotable", "policy owns this rule, not mq-agent"


def test_forcing_review_only_downgrades_and_never_promotes_a_weak_candidate():
    """A weak candidate with a problem stays in inbox; it is not 'review-needed'."""
    factors = {f: 0.0 for f in _FACTORS}
    got = _one(_exports([_item(evidence=[])], {"m-1": _score(factors=factors)}, {}))
    assert got["bucket"] == "inbox"
    assert "missing-evidence" in got["review_reasons"], "the reason is still reported"


def test_provenance_is_deduplicated_and_carries_no_private_detail():
    item = _item(evidence=[{"ref": "observation:o1", "kind": "observation"},
                           {"ref": "observation:o1", "kind": "observation"},
                           {"ref": "observation:o2", "kind": "observation"}])
    evidence = {"observation:o1": _ev(), "observation:o2": _ev(ref="observation:o2", producer="mq-mcp")}
    got = _one(_exports([item], {"m-1": _score()}, evidence))
    assert [p["ref"] for p in got["provenance"]] == ["observation:o1", "observation:o2"]
    assert sorted(p["producer"] for p in got["provenance"]) == ["mq-mcp", "repo-signal"]
    assert all(set(p) == {"ref", "producer", "kind", "observed_at"} for p in got["provenance"])


def test_candidate_without_a_score_record_is_reported_not_guessed():
    """A broken join is reported, never imputed.

    It stays in `inbox` rather than `review-needed`: review-needed is the
    approval queue, and an unscored memory is not something an operator can
    decide to promote. The gap is surfaced as a reason instead.
    """
    got = _one(_exports([_item()], {}, {"observation:o1": _ev()}))
    assert got["bucket"] == "inbox"
    assert "missing-score-record" in got["review_reasons"]
    assert got["ranked_score"] == 0.0
    assert got["contributions"] == {f: 0.0 for f in _FACTORS}


def test_ranking_is_deterministic_and_ordered_by_score():
    items = [_item(id=f"m-{i}", evidence=[{"ref": f"observation:o{i}", "kind": "observation"}])
             for i in (1, 2, 3)]
    scores = {f"m-{i}": _score(memory_id=f"m-{i}", factors={f: float(i) for f in _FACTORS})
              for i in (1, 2, 3)}
    evidence = {f"observation:o{i}": _ev(ref=f"observation:o{i}", candidate=f"m-{i}") for i in (1, 2, 3)}
    exports = _exports(items, scores, evidence)
    first = ip.build_ranking(exports)
    assert [c["memory_id"] for c in first["candidates"]] == ["m-3", "m-2", "m-1"]
    assert first == ip.build_ranking(exports), "same input must give byte-identical output"


def test_counts_match_the_buckets():
    ranking = ip.build_ranking(_exports([_item()], {"m-1": _score()}, {"observation:o1": _ev()}))
    total = sum(ranking["counts"].values())
    assert total == len(ranking["candidates"])
    assert set(ranking["counts"]) == {"inbox", "review-needed", "auto-promotable"}
