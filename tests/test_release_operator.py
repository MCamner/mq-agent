from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.operator.render_release_status import render_release_status
from mq_agent.operator.stack_health import get_stack_health, render_stack_health
from mq_agent.perception.adapter import normalize_perception_output
from mq_agent.perception.contract import validate_perception_payload
from mq_agent.tools.mcp_bridge import MultiMCPBridge

runner = CliRunner()


def sample_gate(status: str = "blocked") -> dict[str, object]:
    return {
        "repo": "mq-agent",
        "target": "v1.4.0",
        "status": status,
        "score": 78,
        "blockers": ["CHANGELOG missing v1.4.0 entry"] if status == "blocked" else [],
        "warnings": ["README mentions old roadmap"] if status == "warning" else [],
        "next_actions": ["Update CHANGELOG"],
        "checks": [
            {
                "name": "learn_hygiene_pass",
                "status": "pass",
                "message": "Learn hygiene pass: records=5, duplicates=0.",
            }
        ],
    }


def test_release_status_json_asks_mq_mcp_gate():
    with patch.object(MultiMCPBridge, "release_gate_run", return_value=sample_gate("warning")) as mock:
        result = runner.invoke(app, ["release", "status", "--repo", ".", "--target", "v1.4.0", "--json"])

    assert result.exit_code == 0
    mock.assert_called_once_with(repo=str(Path(".").expanduser().resolve()), target="v1.4.0", test_command="")
    payload = json.loads(result.output)
    assert payload["status"] == "warning"


def test_release_status_passes_test_command_to_release_gate():
    with patch.object(MultiMCPBridge, "release_gate_run", return_value=sample_gate("pass")) as mock:
        result = runner.invoke(
            app,
            [
                "release",
                "gate",
                "--repo",
                ".",
                "--target",
                "v1.4.0",
                "--test-cmd",
                "uv run pytest -q",
                "--json",
            ],
        )

    assert result.exit_code == 0
    mock.assert_called_once_with(
        repo=str(Path(".").expanduser().resolve()),
        target="v1.4.0",
        test_command="uv run pytest -q",
    )


def test_release_status_run_tests_uses_default_test_command():
    with patch.object(MultiMCPBridge, "release_gate_run", return_value=sample_gate("pass")) as mock:
        result = runner.invoke(app, ["release", "status", "--run-tests", "--json"])

    assert result.exit_code == 0
    mock.assert_called_once_with(
        repo=str(Path(".").expanduser().resolve()),
        target="v1.4.0",
        test_command="uv run pytest -q",
    )


def test_release_status_json_unwraps_mcp_text_payload():
    wrapped = [
        [
            {
                "type": "text",
                "text": json.dumps(sample_gate("warning")),
            }
        ],
        sample_gate("warning"),
    ]
    with patch.object(MultiMCPBridge, "release_gate_run", return_value=wrapped):
        result = runner.invoke(app, ["release", "status", "--repo", ".", "--target", "v1.4.0", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "warning"
    assert payload["repo"] == "mq-agent"


def test_release_status_blocked_exits_nonzero_and_renders_operator_output():
    with patch.object(MultiMCPBridge, "release_gate_run", return_value=sample_gate("blocked")):
        result = runner.invoke(app, ["release", "status"])

    assert result.exit_code == 1
    assert "MQ OPERATOR STATUS" in result.output
    assert "BLOCKED" in result.output
    assert "CHANGELOG" in result.output


def test_release_status_missing_gate_tool_is_blocked():
    missing = {
        "ok": False,
        "error": "mq-mcp tool 'release_gate_run' is not available.",
        "hint": "Start or upgrade mq-mcp.",
    }
    with patch.object(MultiMCPBridge, "release_gate_run", return_value=missing):
        result = runner.invoke(app, ["release", "status", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "blocked"
    assert "release_gate_run" in payload["blockers"][0]


def test_release_renderer_does_not_need_gate_rules():
    output = render_release_status(sample_gate("pass"))

    assert "MQ OPERATOR STATUS" in output
    assert "PASS" in output
    assert "learn_hygiene_pass" in output
    assert "No action required." not in output


def test_release_workflow_json_lists_mqlaunch_entrypoints():
    result = runner.invoke(app, ["release", "workflow", "--repo", ".", "--target", "v1.4.0", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["steps"][0]["name"] == "stack_health"
    assert any("mqlaunch agent release-workflow" in item for item in payload["mqlaunch"])
    assert any("--run-tests" in item for item in payload["mqlaunch"])
    assert any(step["name"] == "review_release" for step in payload["steps"])
    assert any("--run-tests" in step["command"] for step in payload["steps"])


def test_release_prepare_is_dry_run_by_default():
    result = runner.invoke(app, ["release", "prepare", "--repo", ".", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["approved"] is False
    assert payload["status"] == "dry-run"
    assert payload["command"] == "repo-signal export . --all"


def test_review_release_delegates_to_release_gate():
    with patch.object(MultiMCPBridge, "release_gate_run", return_value=sample_gate("warning")) as mock:
        result = runner.invoke(app, ["review", "release", "--repo", ".", "--target", "v1.4.0", "--json"])

    assert result.exit_code == 0
    mock.assert_called_once_with(repo=str(Path(".").expanduser().resolve()), target="v1.4.0", test_command="")
    payload = json.loads(result.output)
    assert payload["status"] == "warning"


def test_perception_contract_validates_minimal_payload():
    payload = {
        "source_type": "screenshot",
        "source_path": "docs/screenshot.png",
        "ocr_text": "",
        "visual_summary": "",
        "risk_signals": [],
        "confidence": "medium",
    }

    assert validate_perception_payload(payload)["ok"] is True


def test_review_perception_json_normalizes_image_ocr_output():
    raw = {"full_text": "Release notes", "confidence": "high", "risk_signals": ["low contrast"]}
    with patch.object(MultiMCPBridge, "call_tool", return_value=raw) as mock:
        result = runner.invoke(app, ["review", "perception", "docs/screenshot.png", "--json"])

    assert result.exit_code == 0
    mock.assert_called_once_with("image_ocr", {"image_path": "docs/screenshot.png"})
    payload = json.loads(result.output)
    assert payload["source_type"] == "screenshot"
    assert payload["ocr_text"] == "Release notes"
    assert payload["contract"]["ok"] is True


def test_review_perception_accepts_fixture_shape_through_mcp_bridge():
    raw = json.loads(Path("tests/fixtures/sample_perception_output.json").read_text(encoding="utf-8"))

    normalized = normalize_perception_output("docs/screenshot.png", raw)
    assert normalized["contract"]["ok"] is True

    with patch.object(MultiMCPBridge, "call_tool", return_value=raw) as mock:
        result = runner.invoke(app, ["review", "perception", "docs/screenshot.png", "--json"])

    assert result.exit_code == 0
    mock.assert_called_once_with("image_ocr", {"image_path": "docs/screenshot.png"})
    payload = json.loads(result.output)
    assert payload["visual_summary"] == raw["visual_summary"]
    assert payload["detected_regions"] == raw["detected_regions"]
    assert payload["risk_signals"] == raw["risk_signals"]
    assert payload["contract"]["ok"] is True


def test_stack_health_reports_core_components(monkeypatch):
    monkeypatch.setattr(
        MultiMCPBridge,
        "get_server_statuses",
        lambda self: {
            "mq-mcp": {"available": True, "endpoint": "http://localhost:8765", "tools": 100},
            "mq-image-analyze": {"available": False, "endpoint": "http://localhost:8766", "tools": 0},
        },
    )
    monkeypatch.setattr("mq_agent.mcp.manager.read_pid", lambda: 123)
    monkeypatch.setattr("mq_agent.mcp.manager.is_running", lambda: True)
    monkeypatch.setattr("mq_agent.tools.signal_tools.signal_available", lambda: True)
    monkeypatch.setattr("shutil.which", lambda name: "/bin/mq-hal" if name == "mq-hal" else None)

    report = get_stack_health()

    assert report["status"] == "warning"
    names = {item["name"]: item for item in report["components"]}
    assert names["mq-agent"]["status"] == "pass"
    assert names["mq-mcp"]["status"] == "pass"
    assert names["repo-signal"]["status"] == "pass"
    assert names["mq-image-analyze"]["status"] == "warning"
    assert names["mq-hal"]["status"] == "pass"
    assert "mq-image-analyze" in render_stack_health(report)


def test_dashboard_json_outputs_stack_health(monkeypatch):
    monkeypatch.setattr(
        "mq_agent.operator.stack_health.get_stack_health",
        lambda: {"status": "pass", "components": [{"name": "mq-agent", "status": "pass", "detail": "CLI available"}]},
    )

    result = runner.invoke(app, ["dashboard", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "pass"
    assert payload["components"][0]["name"] == "mq-agent"
