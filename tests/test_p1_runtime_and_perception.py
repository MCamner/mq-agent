from __future__ import annotations

import hashlib
import json
from unittest.mock import patch

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.execution_outcome import build_execution_outcome

runner = CliRunner()


def test_execution_outcome_accepts_measured_structured_fallback() -> None:
    fallback = {
        "from": "mq-mcp-tool-policy",
        "to": "static-read-only-allowlist",
        "reason": "policy-unavailable-or-invalid",
        "stage": "workflow-policy",
        "source": "measured",
    }
    outcome = build_execution_outcome(
        runtime="task-runner",
        task_class="task",
        result="PASS",
        exit_status="ok",
        latency_ms=7,
        fallbacks=1,
        fallback=fallback,
    )

    assert outcome["fallbacks"] == 1
    assert outcome["fallback"] == fallback


def _perception() -> dict:
    return {
        "schema_version": "perception.v1",
        "evidence_id": "sha256:" + "a" * 64,
        "source_type": "ui",
        "source_path": "screen.png",
        "ocr_text": "DELETE",
        "visual_summary": "Dangerous action is visible.",
        "detected_regions": [],
        "risk_signals": ["destructive action exposed"],
        "confidence": "high",
        "limitations": ["visual evidence only"],
    }


def _perception_review() -> dict:
    perception = _perception()
    return {
        "schema": "mq.perception-review.v1",
        "review_id": "sha256:" + "b" * 64,
        "status": "WARNING",
        "producer": "ui",
        "mode": "risk",
        "perception_ref": {
            "schema_version": "perception.v1",
            "evidence_id": perception["evidence_id"],
            "source_type": "ui",
            "confidence": "high",
        },
        "perception": perception,
        "reviewer": {
            "schema": "mq.runtime-identity.v1",
            "component": "mq-mcp",
            "version": "2.1.0",
            "commit": "c" * 40,
        },
        "review": {
            "summary": "Review findings: WARNING=1",
            "findings": [
                {
                    "severity": "WARNING",
                    "category": "producer-risk",
                    "message": "destructive action exposed",
                    "evidence_refs": [perception["evidence_id"]],
                    "source": "producer",
                }
            ],
            "risk_signals": ["destructive action exposed"],
            "limitations": ["visual evidence only"],
            "confidence": "high",
            "model_reinterpretation": False,
        },
    }


def _perception_receipt(review: dict, *, review_id: str | None = None) -> dict:
    core = {
        "schema": "mq.perception-review-receipt.v1",
        "status": "ISSUED",
        "reason": "perception-and-review-content-addresses-bound",
        "perception_evidence_id": review["perception_ref"]["evidence_id"],
        "review_id": review_id or review["review_id"],
        "reviewer": review["reviewer"],
        "repository": {
            "repo": "demo",
            "commit": "d" * 40,
            "worktree_clean": True,
        },
    }
    raw = json.dumps(
        core, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return {
        "receipt_id": "sha256:" + hashlib.sha256(raw).hexdigest(),
        **core,
    }


class _PerceptionBridge:
    def __init__(self, *, bad_receipt: bool = False):
        self.bad_receipt = bad_receipt
        self.review_calls: list[dict] = []

    def image_perception(self, image_path, *, producer, source_type=None):
        assert image_path == "screen.png"
        assert producer == "ui"
        assert source_type == "ui"
        return _perception()

    def review_perception(
        self,
        perception,
        *,
        producer,
        mode="risk",
        receipt=False,
        repo_path=None,
    ):
        self.review_calls.append(
            {
                "perception": perception,
                "producer": producer,
                "mode": mode,
                "receipt": receipt,
                "repo_path": repo_path,
            }
        )
        review = _perception_review()
        if not receipt:
            return review
        bad_id = "sha256:" + "e" * 64 if self.bad_receipt else None
        return {
            "review": review,
            "receipt": _perception_receipt(review, review_id=bad_id),
        }


def test_review_perception_delegates_to_mq_mcp_and_preserves_evidence() -> None:
    bridge = _PerceptionBridge()
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(
            app,
            [
                "review",
                "perception",
                "screen.png",
                "--producer",
                "ui",
                "--source-type",
                "ui",
                "--mode",
                "risk",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == "mq.perception-review.v1"
    assert payload["status"] == "WARNING"
    assert payload["review"]["risk_signals"] == ["destructive action exposed"]
    assert payload["review"]["model_reinterpretation"] is False
    assert payload["review"]["findings"][0]["evidence_refs"] == [
        _perception()["evidence_id"]
    ]
    assert bridge.review_calls[0]["perception"] == _perception()


def test_review_perception_receipt_binds_review_and_repo_commit(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("MQ_AGENT_REVIEW_RECEIPTS_DIR", str(tmp_path))
    bridge = _PerceptionBridge()
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(
            app,
            [
                "review",
                "perception",
                "screen.png",
                "--producer",
                "ui",
                "--source-type",
                "ui",
                "--receipt",
                "--repo",
                ".",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    receipt = payload["receipt"]
    assert receipt["review_id"] == payload["review"]["review_id"]
    assert receipt["perception_evidence_id"] == payload["review"]["perception_ref"]["evidence_id"]
    assert receipt["repository"]["commit"] == "d" * 40
    assert len(list(tmp_path.glob("*.json"))) == 1
    serialized = json.dumps(receipt)
    assert "ocr_text" not in serialized
    assert "source_path" not in serialized


def test_review_perception_refuses_mismatched_receipt_binding(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MQ_AGENT_REVIEW_RECEIPTS_DIR", str(tmp_path))
    bridge = _PerceptionBridge(bad_receipt=True)
    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=bridge):
        result = runner.invoke(
            app,
            [
                "review",
                "perception",
                "screen.png",
                "--receipt",
                "--repo",
                ".",
                "--json",
            ],
        )

    assert result.exit_code == 1
    assert "binding/content address is invalid" in result.output
    assert list(tmp_path.glob("*.json")) == []

