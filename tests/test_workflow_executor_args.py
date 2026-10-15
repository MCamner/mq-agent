"""Real target arguments fail closed; no server-cwd or registry-name fallback."""

from typing import Any, cast
import pytest
from mq_agent.workflows.runner import MCPBridgeExecutor


class RecordingBridge:
    def __init__(self):
        self.calls = []

    def call_tool(self, tool, payload):
        self.calls.append((tool, payload))
        return {"ok": True}


def executor(monkeypatch):
    monkeypatch.setattr(
        "mq_agent.workflows.target.resolve_target",
        lambda repo: {"root": "/target/a", "commit": "a" * 40},
    )
    ex = MCPBridgeExecutor.__new__(MCPBridgeExecutor)
    ex._bridge = cast(Any, RecordingBridge())
    return ex


def test_only_supported_target_argument_is_sent(monkeypatch):
    ex = executor(monkeypatch)
    ex("run_tests", {}, "/target/a/sub")
    assert ex._bridge.calls == [("run_tests", {"repo_path": "/target/a"})]


def test_caller_cannot_override_target(monkeypatch):
    ex = executor(monkeypatch)
    with pytest.raises(ValueError, match="conflicts"):
        ex("git_diff", {"repo_path": "/other"}, "/target/a")
    with pytest.raises(ValueError, match="overrides"):
        ex("run_tests", {"repo_name": "other"}, "/target/a")
    assert ex._bridge.calls == []


def test_launcher_service_tools_get_no_invented_arguments(monkeypatch):
    ex = executor(monkeypatch)
    ex("run_mqlaunch_doctor", {}, "/target/a")
    assert ex._bridge.calls == [("run_mqlaunch_doctor", {})]
