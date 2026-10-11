from datetime import UTC, datetime, timedelta
import json

import pytest

from tests.test_hybrid_retrieval_evidence import positive_proposals  # noqa: F401

NOW = datetime(2026, 10, 11, tzinfo=UTC)
REVISION = "a" * 40


@pytest.fixture
def approval_context(positive_proposals):  # noqa: F811 - imported pytest fixture
    root, challenge, admission, plans = positive_proposals
    plan = next(p for p in plans if p["task_class"] == "repo-review")
    return dict(
        policy_plan_id=plan["policy_plan_id"],
        challenge_id=challenge["challenge_id"],
        task_class="repo-review",
        channel="notebook-keyword",
        catalog_path=root.parent / "catalog.json",
        runtime_revision=REVISION,
        max_additional_tokens=2000,
        optional_timeout_ms=1000,
        validity_seconds=3600,
        reason="Operator reviewed bounded keyword evidence",
        state_root=root,
    )


def _approve(context, **changes):
    from mq_agent.memory.hybrid_runtime import approve_hybrid_policy

    return approve_hybrid_policy(**(context | changes), approve=True, now=NOW)


def _verify(context, receipt, **changes):
    from mq_agent.memory.hybrid_runtime import verify_hybrid_approval

    args = {
        k: context[k]
        for k in (
            "task_class",
            "channel",
            "catalog_path",
            "runtime_revision",
            "state_root",
        )
    }
    return verify_hybrid_approval(receipt["approval_id"], **(args | changes), now=NOW)


def test_approval_binds_evidence_budget_and_current_inputs(approval_context):
    receipt = _approve(approval_context)
    assert receipt["schema"] == "mq.hybrid-retrieval-approval.v1"
    assert receipt["policy_plan_id"] == approval_context["policy_plan_id"]
    assert receipt["challenge_id"] == approval_context["challenge_id"]
    assert receipt["budget"] == {
        "max_additional_tokens": 2000,
        "optional_timeout_ms": 1000,
        "token_measurement": "additional-json-chars-div-4",
    }
    assert receipt["runtime_consumption_available"] is False
    result = _verify(approval_context, receipt)
    assert result["status"] == "VERIFIED"
    assert result["errors"] == []
    assert str(approval_context["catalog_path"]) not in json.dumps(receipt)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_additional_tokens", 0),
        ("max_additional_tokens", True),
        ("optional_timeout_ms", -1),
        ("optional_timeout_ms", 1.5),
        ("validity_seconds", 0),
        ("reason", ""),
        ("runtime_revision", "unknown"),
        ("task_class", "ci"),
        ("channel", "codegraph"),
    ],
)
def test_approval_refuses_invalid_budget_or_scope(approval_context, field, value):
    with pytest.raises(ValueError):
        _approve(approval_context, **{field: value})
    assert not (approval_context["state_root"] / "approvals").exists()


def test_approval_requires_explicit_permission(approval_context):
    from mq_agent.memory.hybrid_runtime import approve_hybrid_policy

    with pytest.raises(ValueError, match="explicit approval"):
        approve_hybrid_policy(**approval_context, now=NOW)


@pytest.mark.parametrize(
    "damage",
    [
        "expired",
        "future",
        "revision",
        "catalog",
        "class",
        "channel",
        "receipt",
        "evidence",
    ],
)
def test_approval_verification_refuses_stale_or_tampered_state(
    approval_context, damage
):
    from mq_agent.memory.hybrid_runtime import verify_hybrid_approval

    receipt = _approve(approval_context)
    context = dict(approval_context)
    time = NOW
    if damage == "expired":
        time += timedelta(seconds=3600)
    elif damage == "future":
        time -= timedelta(seconds=1)
    elif damage == "revision":
        context["runtime_revision"] = "b" * 40
    elif damage == "catalog":
        context["catalog_path"].write_text("{}")
    elif damage == "class":
        context["task_class"] = "docs"
    elif damage == "channel":
        context["channel"] = "notebook-vector"
    elif damage == "receipt":
        path = next((context["state_root"] / "approvals").glob("*.json"))
        record = json.loads(path.read_text())
        record["budget"]["max_additional_tokens"] = 999999
        path.write_text(json.dumps(record))
    else:
        next((context["state_root"] / "runs").glob("*.json")).unlink()
    args = {
        k: context[k]
        for k in (
            "task_class",
            "channel",
            "catalog_path",
            "runtime_revision",
            "state_root",
        )
    }
    result = verify_hybrid_approval(receipt["approval_id"], **args, now=time)
    assert result["status"] == "REFUSED"
    assert result["errors"]


def test_approval_refuses_catalog_not_measured_in_evidence(approval_context):
    approval_context["catalog_path"].write_text("{}")
    with pytest.raises(ValueError, match="catalog"):
        _approve(approval_context)


def test_revocation_is_exact_append_only_and_cannot_toggle(approval_context):
    from mq_agent.memory.hybrid_runtime import revoke_hybrid_approval

    first = _approve(approval_context)
    second = _approve(approval_context, max_additional_tokens=3000)
    root = approval_context["state_root"]
    original = {p: p.read_bytes() for p in (root / "approvals").glob("*.json")}
    with pytest.raises(ValueError, match="explicit approval"):
        revoke_hybrid_approval(
            first["approval_id"], reason="withdrawn", state_root=root
        )
    revocation = revoke_hybrid_approval(
        first["approval_id"], reason="withdrawn", approve=True, state_root=root, now=NOW
    )
    assert revocation["approval_id"] == first["approval_id"]
    assert _verify(approval_context, first)["status"] == "REFUSED"
    assert _verify(approval_context, second)["status"] == "VERIFIED"
    assert all(p.read_bytes() == contents for p, contents in original.items())
    with pytest.raises(ValueError, match="already revoked"):
        revoke_hybrid_approval(
            first["approval_id"], reason="again", approve=True, state_root=root, now=NOW
        )


def test_approval_cli_permission_identity_status_and_revocation(
    approval_context, monkeypatch
):
    from types import SimpleNamespace
    from typer.testing import CliRunner
    from mq_agent.main import app

    context = approval_context
    args = [
        "memory",
        "hybrid-evidence",
        "approval",
        context["policy_plan_id"],
        "--challenge-id",
        context["challenge_id"],
        "--catalog",
        str(context["catalog_path"]),
        "--max-additional-tokens",
        "2000",
        "--optional-timeout-ms",
        "1000",
        "--validity-seconds",
        "3600",
        "--reason",
        "reviewed",
        "--state-root",
        str(context["state_root"]),
        "--json",
    ]
    runner = CliRunner()
    result = runner.invoke(app, args)
    assert result.exit_code == 2
    assert "explicit approval" in result.output
    assert not (context["state_root"] / "approvals").exists()
    monkeypatch.setattr(
        "mq_agent.core.runtime_guard.check",
        lambda: SimpleNamespace(allowed=False, identity=None, reason="dirty-worktree"),
    )
    result = runner.invoke(app, args + ["--approve"])
    assert result.exit_code == 2
    assert "dirty-worktree" in result.output
    assert not (context["state_root"] / "approvals").exists()
    monkeypatch.setattr(
        "mq_agent.core.runtime_guard.check",
        lambda: SimpleNamespace(
            allowed=True, identity={"commit": REVISION}, reason="verified"
        ),
    )
    result = runner.invoke(app, args + ["--approve"])
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output)
    assert receipt["runtime_revision"] == REVISION
    status_args = [
        "memory",
        "hybrid-evidence",
        "approval-status",
        receipt["approval_id"],
        "--catalog",
        str(context["catalog_path"]),
        "--state-root",
        str(context["state_root"]),
        "--json",
    ]
    result = runner.invoke(app, status_args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "VERIFIED"
    revoke_args = [
        "memory",
        "hybrid-evidence",
        "approval-revoke",
        receipt["approval_id"],
        "--reason",
        "withdrawn",
        "--state-root",
        str(context["state_root"]),
        "--json",
    ]
    assert runner.invoke(app, revoke_args).exit_code == 2
    result = runner.invoke(app, revoke_args + ["--approve"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["approval_id"] == receipt["approval_id"]
    result = runner.invoke(app, status_args)
    assert result.exit_code == 1
    assert json.loads(result.output)["status"] == "REFUSED"
    assert runner.invoke(app, revoke_args + ["--approve"]).exit_code == 2


@pytest.mark.parametrize("damage", ["tampered", "symlink", "directory"])
def test_corrupt_revocation_fails_closed(approval_context, damage, tmp_path):
    from mq_agent.memory.hybrid_runtime import revoke_hybrid_approval
    from mq_agent.memory.hybrid_evidence import HybridEvidenceStore

    receipt = _approve(approval_context)
    root = approval_context["state_root"]
    revoke_hybrid_approval(
        receipt["approval_id"],
        reason="withdrawn",
        approve=True,
        state_root=root,
        now=NOW,
    )
    path = HybridEvidenceStore(root)._path(
        "approval-revocations", receipt["approval_id"]
    )
    if damage == "tampered":
        path.write_text("{}")
    else:
        path.unlink()
        if damage == "symlink":
            path.symlink_to(tmp_path / "missing-revocation")
        else:
            path.mkdir()
    assert _verify(approval_context, receipt)["status"] == "REFUSED"


def _retrieve(context, receipt=None, **changes):
    from mq_agent.memory.hybrid_runtime import retrieve_hybrid_memory

    args = dict(
        query="MCP orchestration",
        task_class="repo-review",
        approval_id=receipt["approval_id"] if receipt else None,
        catalog_path=context["catalog_path"],
        runtime_revision=REVISION,
        state_root=context["state_root"],
        now=NOW,
        active_search=lambda query: {
            "results": [{"id": "active-1", "content": "original"}]
        },
    )
    args.update(changes)
    return retrieve_hybrid_memory(**args)


def test_consumer_default_is_active_only_and_preserves_active_result(
    approval_context, monkeypatch
):
    def forbidden(*args, **kwargs):
        pytest.fail("optional search invoked without opt-in")

    monkeypatch.setattr(
        "mq_agent.memory.hybrid_runtime._keyword_search", forbidden, raising=False
    )
    result = _retrieve(approval_context)
    assert result["status"] == "PASS"
    assert result["mode"] == "ACTIVE_ONLY"
    assert result["active_result"] == {
        "results": [{"id": "active-1", "content": "original"}]
    }
    assert result["trace"]["fallback_reason"] is None
    assert result["trace"]["effective_channel_selection"]["notebook_keyword"] is False


def test_consumer_uses_approved_keyword_refs_without_writing_state(approval_context):
    receipt = _approve(approval_context, optional_timeout_ms=5000)
    root = approval_context["state_root"]
    before = {p: p.read_bytes() for p in root.rglob("*.json")}
    result = _retrieve(approval_context, receipt)
    assert result["status"] == "PASS"
    assert result["mode"] == "HYBRID"
    assert {(row["namespace"], row["reference"]) for row in result["refs"]} == {
        ("semantic-memory", "active-1"),
        ("notebook", "doc-1"),
    }
    assert result["trace"]["approval_id"] == receipt["approval_id"]
    assert result["trace"]["effective_channel_selection"] == {
        "notebook_keyword": True,
        "notebook_vector": False,
        "codegraph": False,
    }
    assert result["trace"]["additional_token_estimate"] <= 2000
    assert result["trace"]["optional_latency_ms"] <= 5000
    trace = json.dumps(result["trace"])
    assert "MCP orchestration" not in trace
    assert str(approval_context["catalog_path"]) not in trace
    assert "doc-1" not in trace
    assert {p: p.read_bytes() for p in root.rglob("*.json")} == before


@pytest.mark.parametrize(
    "cause",
    [
        "revoked",
        "disabled",
        "unknown-class",
        "budget",
        "failure",
        "timeout",
        "changed-catalog",
        "revision",
    ],
)
def test_consumer_fallback_preserves_active_only(approval_context, monkeypatch, cause):
    import subprocess
    from mq_agent.memory.hybrid_runtime import revoke_hybrid_approval

    receipt = _approve(
        approval_context, max_additional_tokens=1 if cause == "budget" else 2000
    )
    changes = {}
    if cause == "revoked":
        revoke_hybrid_approval(
            receipt["approval_id"],
            reason="withdrawn",
            approve=True,
            state_root=approval_context["state_root"],
            now=NOW,
        )
    elif cause == "disabled":
        monkeypatch.setenv("MQ_HYBRID_CONSUMPTION", "off")
    elif cause == "unknown-class":
        changes["task_class"] = "unknown"
    elif cause == "revision":
        changes["runtime_revision"] = "b" * 40
    elif cause == "changed-catalog":
        approval_context["catalog_path"].write_text("{}")
    elif cause in {"failure", "timeout"}:

        def broken(*args, **kwargs):
            if cause == "timeout":
                raise subprocess.TimeoutExpired("keyword worker", 0.001)
            raise RuntimeError("optional failed")

        monkeypatch.setattr("mq_agent.memory.hybrid_runtime._keyword_search", broken)
    baseline = _retrieve(approval_context)
    result = _retrieve(approval_context, receipt, **changes)
    assert result["status"] == "PASS"
    assert result["mode"] == "ACTIVE_ONLY"
    assert result["refs"] == baseline["refs"]
    assert result["active_result"] == baseline["active_result"]
    assert result["trace"]["fallback_reason"]
    assert result["trace"]["effective_channel_selection"]["notebook_keyword"] is False


@pytest.mark.parametrize("raw", [{"ok": False, "error": "unavailable"}, None])
def test_consumer_never_substitutes_optional_for_unavailable_active(
    approval_context, raw, monkeypatch
):
    receipt = _approve(approval_context)
    monkeypatch.setattr(
        "mq_agent.memory.hybrid_runtime._keyword_search",
        lambda *args, **kwargs: pytest.fail("must not use optional"),
    )
    result = _retrieve(approval_context, receipt, active_search=lambda query: raw)
    assert result["status"] == "UNAVAILABLE"
    assert result["refs"] == []


def test_consumer_keyword_worker_has_real_deadline(approval_context, monkeypatch):
    import subprocess
    import sys
    import time
    from mq_agent.memory import hybrid_runtime

    receipt = _approve(approval_context, optional_timeout_ms=30)
    original = subprocess.run

    def delayed(*args, **kwargs):
        return original(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            capture_output=True,
            text=True,
            timeout=kwargs["timeout"],
        )

    monkeypatch.setattr(hybrid_runtime.subprocess, "run", delayed)
    start = time.monotonic()
    result = _retrieve(approval_context, receipt)
    assert time.monotonic() - start < 2
    assert result["trace"]["fallback_reason"] == "optional-timeout"
    assert result["mode"] == "ACTIVE_ONLY"


def test_consumer_cli_default_opt_in_fallback_and_active_failure(
    approval_context, monkeypatch
):
    from types import SimpleNamespace
    from typer.testing import CliRunner
    from mq_agent.main import app
    from mq_agent.memory import hybrid_runtime

    monkeypatch.setattr(hybrid_runtime, "_now", lambda value: value or NOW)
    receipt = _approve(approval_context, optional_timeout_ms=5000)
    monkeypatch.setattr(
        "mq_agent.memory.hybrid_retrieval._default_active_search",
        lambda query: {"results": [{"id": "active-1"}]},
    )
    monkeypatch.setattr(
        "mq_agent.core.runtime_guard.check",
        lambda: SimpleNamespace(
            allowed=True, identity={"commit": REVISION}, reason="verified"
        ),
    )
    base = ["memory", "retrieve", "MCP orchestration", "--json"]
    extra = [
        "--approval-id",
        receipt["approval_id"],
        "--catalog",
        str(approval_context["catalog_path"]),
        "--state-root",
        str(approval_context["state_root"]),
    ]
    runner = CliRunner()
    result = runner.invoke(app, base)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["mode"] == "ACTIVE_ONLY"
    result = runner.invoke(app, base + extra)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["mode"] == "HYBRID"
    monkeypatch.setattr(
        "mq_agent.core.runtime_guard.check",
        lambda: SimpleNamespace(allowed=False, identity=None, reason="dirty-worktree"),
    )
    result = runner.invoke(app, base + extra)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["mode"] == "ACTIVE_ONLY"
    monkeypatch.setattr(
        "mq_agent.memory.hybrid_retrieval._default_active_search",
        lambda query: {"ok": False, "error": "unavailable"},
    )
    result = runner.invoke(app, base + extra)
    assert result.exit_code == 1, result.output
    assert json.loads(result.output)["status"] == "UNAVAILABLE"


@pytest.mark.parametrize("change", ["revocation", "kill-switch", "catalog"])
def test_consumer_rechecks_authorization_after_optional_search(
    approval_context, monkeypatch, change
):
    from mq_agent.memory import hybrid_runtime

    receipt = _approve(approval_context)

    def search(*args, **kwargs):
        if change == "revocation":
            hybrid_runtime.revoke_hybrid_approval(
                receipt["approval_id"],
                reason="withdrawn",
                approve=True,
                state_root=approval_context["state_root"],
                now=NOW,
            )
        elif change == "kill-switch":
            monkeypatch.setenv("MQ_HYBRID_CONSUMPTION", "off")
        else:
            approval_context["catalog_path"].write_text("{}")
        return [{"namespace": "notebook", "reference": "doc-1"}]

    monkeypatch.setattr(hybrid_runtime, "_keyword_search", search)
    result = _retrieve(approval_context, receipt)
    assert result["mode"] == "ACTIVE_ONLY"
    assert result["trace"]["fallback_reason"] in {
        "approval-refused",
        "consumption-disabled",
    }
    assert all(row["namespace"] == "semantic-memory" for row in result["refs"])


def test_consumer_accepts_exact_budget_and_rejects_one_token_below(
    approval_context, monkeypatch
):
    from mq_agent.memory import hybrid_runtime

    refs = [{"namespace": "notebook", "reference": "doc-1"}]
    expected = (
        len(json.dumps(refs, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        + 3
    ) // 4
    monkeypatch.setattr(hybrid_runtime, "_keyword_search", lambda *args: refs)
    good = _approve(approval_context, max_additional_tokens=expected)
    result = _retrieve(approval_context, good)
    assert result["mode"] == "HYBRID"
    assert result["trace"]["additional_token_estimate"] == expected
    small = _approve(approval_context, max_additional_tokens=expected - 1)
    result = _retrieve(approval_context, small)
    assert result["mode"] == "ACTIVE_ONLY"
    assert result["trace"]["fallback_reason"] == "optional-budget-exceeded"


def test_consumer_scope_cannot_change_measured_top_k(approval_context, tmp_path):
    from tests.test_hybrid_retrieval_evidence import (
        _write_challenge_suite,
        _active,
        _codegraph,
    )
    from mq_agent.memory.hybrid_evidence import (
        collect_hybrid_challenge,
        evaluate_hybrid_admission,
        plan_hybrid_runtime_policy,
    )
    from mq_agent.memory.hybrid_runtime import approve_hybrid_policy

    folder = tmp_path / "other-top-k"
    folder.mkdir()
    suite = _write_challenge_suite(folder)
    payload = json.loads(suite.read_text())
    payload["top_k"] = 5
    suite.write_text(json.dumps(payload))
    root = folder / "state"
    challenge = collect_hybrid_challenge(
        suite, state_root=root, active_search=_active, codegraph_search=_codegraph
    )
    admission = evaluate_hybrid_admission(challenge["ablation_id"], state_root=root)
    plan = plan_hybrid_runtime_policy(
        admission["admission_id"], "repo-review", state_root=root
    )
    with pytest.raises(ValueError, match="measured top-k=10"):
        approve_hybrid_policy(
            plan["policy_plan_id"],
            challenge_id=challenge["challenge_id"],
            task_class="repo-review",
            channel="notebook-keyword",
            catalog_path=folder / "catalog.json",
            runtime_revision=REVISION,
            max_additional_tokens=2000,
            optional_timeout_ms=1000,
            validity_seconds=3600,
            reason="reviewed",
            approve=True,
            state_root=root,
            now=NOW,
        )
