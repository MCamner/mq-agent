from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.execution_outcome import build_execution_outcome

runner = CliRunner()
EVIDENCE_ID = "sha256:" + "1" * 64
REVIEW_ID = "sha256:" + "2" * 64
RECEIPT_ID = "sha256:" + "3" * 64


def _perception() -> dict:
    return {
        "schema_version": "perception.v1",
        "evidence_id": EVIDENCE_ID,
        "source_type": "ui",
        "source_path": "screen.png",
        "ocr_text": "DELETE",
        "visual_summary": "Dangerous action is visible.",
        "detected_regions": [],
        "risk_signals": ["destructive action exposed"],
        "confidence": "high",
        "limitations": ["visual evidence only"],
    }


def _review() -> dict:
    perception = _perception()
    return {
        "schema": "mq.perception-review.v1",
        "review_id": REVIEW_ID,
        "status": "WARNING",
        "producer": "ui",
        "mode": "risk",
        "perception_ref": {
            "schema_version": "perception.v1",
            "evidence_id": EVIDENCE_ID,
            "source_type": "ui",
            "confidence": "high",
        },
        "perception": perception,
        "reviewer": {
            "schema": "mq.runtime-identity.v1",
            "component": "mq-mcp",
            "version": "2.1.0",
            "commit": "abcdef1",
        },
        "review": {
            "summary": "Review findings: WARNING=1",
            "findings": [
                {
                    "severity": "WARNING",
                    "category": "producer-risk",
                    "message": "destructive action exposed",
                    "evidence_refs": [EVIDENCE_ID],
                    "source": "producer",
                }
            ],
            "risk_signals": ["destructive action exposed"],
            "limitations": ["visual evidence only"],
            "confidence": "high",
            "model_reinterpretation": False,
        },
    }


def _receipt(status: str = "ISSUED") -> dict:
    return {
        "schema": "mq.perception-review-receipt.v1",
        "receipt_id": RECEIPT_ID,
        "status": status,
        "reason": (
            "perception-and-review-content-addresses-bound"
            if status == "ISSUED"
            else "repository-commit-unavailable"
        ),
        "perception_evidence_id": EVIDENCE_ID,
        "review_id": REVIEW_ID,
        "reviewer": _review()["reviewer"],
        "repository": {
            "repo": "demo",
            "commit": "0123456789abcdef" if status == "ISSUED" else None,
            "worktree_clean": True if status == "ISSUED" else None,
        },
    }


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


def test_review_perception_routes_content_addressed_evidence_through_mq_mcp() -> None:
    calls: list[dict] = []

    class Bridge:
        def image_perception(self, image_path, *, producer, source_type=None):
            assert image_path == "screen.png"
            assert producer == "ui"
            assert source_type == "ui"
            return [{"type": "text", "text": json.dumps(_perception())}]

        def review_perception(
            self,
            perception,
            *,
            producer,
            mode="risk",
            receipt=False,
            repo_path=None,
        ):
            calls.append(
                {
                    "perception": perception,
                    "producer": producer,
                    "mode": mode,
                    "receipt": receipt,
                    "repo_path": repo_path,
                }
            )
            return [{"type": "text", "text": json.dumps(_review())}]

    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=Bridge()):
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
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == "mq.perception-review.v1"
    assert payload["perception_ref"]["evidence_id"] == EVIDENCE_ID
    assert payload["review"]["risk_signals"] == ["destructive action exposed"]
    assert payload["review"]["model_reinterpretation"] is False
    assert calls == [
        {
            "perception": _perception(),
            "producer": "ui",
            "mode": "risk",
            "receipt": False,
            "repo_path": None,
        }
    ]


def test_review_perception_receipt_binds_exact_review_and_repo_commit() -> None:
    class Bridge:
        def image_perception(self, image_path, *, producer, source_type=None):
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
            assert receipt is True
            assert repo_path == "/repo"
            return {"review": _review(), "receipt": _receipt()}

    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=Bridge()):
        result = runner.invoke(
            app,
            [
                "review",
                "perception",
                "screen.png",
                "--receipt",
                "--repo",
                "/repo",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["receipt"]["status"] == "ISSUED"
    assert payload["receipt"]["perception_evidence_id"] == EVIDENCE_ID
    assert payload["receipt"]["review_id"] == REVIEW_ID
    assert payload["receipt"]["repository"]["commit"] == "0123456789abcdef"
    serialized = json.dumps(payload["receipt"])
    for forbidden in ("ocr_text", "detected_regions", "source_path", "base64"):
        assert forbidden not in serialized


def test_review_perception_refuses_an_unbound_requested_receipt() -> None:
    class Bridge:
        def image_perception(self, image_path, *, producer, source_type=None):
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
            return {"review": _review(), "receipt": _receipt("REFUSED")}

    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=Bridge()):
        result = runner.invoke(
            app,
            [
                "review",
                "perception",
                "screen.png",
                "--receipt",
                "--repo",
                "/missing",
                "--json",
            ],
        )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["receipt"]["status"] == "REFUSED"
    assert payload["receipt"]["reason"] == "repository-commit-unavailable"


def test_review_perception_rejects_malformed_evidence_before_review() -> None:
    called = False

    class Bridge:
        def image_perception(self, image_path, *, producer, source_type=None):
            payload = _perception()
            payload["evidence_id"] = "not-a-content-address"
            return payload

        def review_perception(self, *args, **kwargs):
            nonlocal called
            called = True
            return _review()

    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge", return_value=Bridge()):
        result = runner.invoke(
            app,
            ["review", "perception", "screen.png", "--json"],
        )

    assert result.exit_code == 1
    assert called is False
    payload = json.loads(result.output)
    assert "evidence_id" in payload["error"]
