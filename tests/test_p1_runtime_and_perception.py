from __future__ import annotations

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


def test_review_perception_delegates_and_preserves_risks() -> None:
    class Bridge:
        def image_perception(self, image_path, *, producer, source_type=None):
            assert image_path == "screen.png"
            assert producer == "ui"
            return {
                "source_type": source_type or "ui",
                "source_path": "screen.png",
                "ocr_text": "DELETE",
                "visual_summary": "Dangerous action is visible.",
                "detected_regions": [],
                "risk_signals": ["destructive action exposed"],
                "confidence": "high",
                "limitations": ["visual evidence only"],
            }

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
    assert payload["status"] == "WARNING"
    assert payload["review"]["risk_signals"] == ["destructive action exposed"]
    assert payload["review"]["model_reinterpretation"] is False
