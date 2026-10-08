from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from mq_agent.memory.codegraph_runtime import search_codegraph


class _NoCodeGraphBridge:
    def list_tool_specs(self):
        return []

    def call_tool(self, tool_name, args):  # pragma: no cover - must never run
        raise AssertionError((tool_name, args))


def test_prefers_connected_codegraph_mcp(monkeypatch, tmp_path: Path) -> None:
    calls = []

    class FakeBridge:
        def list_tool_specs(self):
            return [SimpleNamespace(name="codegraph_explore")]

        def call_tool(self, tool_name, args):
            calls.append((tool_name, args))
            return {"results": [{"path": "mq_agent/main.py", "symbol": "app"}]}

    monkeypatch.setattr(
        "mq_agent.tools.mcp_bridge.MultiMCPBridge",
        FakeBridge,
    )

    result = search_codegraph("how does routing work", tmp_path)

    assert result["results"][0]["symbol"] == "app"
    assert calls == [
        (
            "codegraph_explore",
            {
                "query": "how does routing work",
                "projectPath": str(tmp_path.resolve()),
            },
        )
    ]


def test_falls_back_to_local_cli_for_indexed_repo(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".codegraph").mkdir()
    calls = []

    monkeypatch.setattr(
        "mq_agent.tools.mcp_bridge.MultiMCPBridge",
        _NoCodeGraphBridge,
    )
    monkeypatch.setattr(
        "mq_agent.memory.codegraph_runtime.shutil.which",
        lambda name: "/usr/local/bin/codegraph" if name == "codegraph" else None,
    )

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout="CodeGraph answer",
            stderr="",
        )

    monkeypatch.setattr(
        "mq_agent.memory.codegraph_runtime.subprocess.run",
        fake_run,
    )

    result = search_codegraph("trace hybrid retrieval", tmp_path)

    assert result == "CodeGraph answer"
    assert calls == [
        (
            ["/usr/local/bin/codegraph", "explore", "trace hybrid retrieval"],
            {
                "cwd": tmp_path.resolve(),
                "capture_output": True,
                "text": True,
                "timeout": 30,
                "check": False,
            },
        )
    ]


def test_missing_local_index_is_unavailable_without_cli_call(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "mq_agent.tools.mcp_bridge.MultiMCPBridge",
        _NoCodeGraphBridge,
    )

    def forbidden_which(_name):
        raise AssertionError("CLI lookup must not run without a CodeGraph index")

    monkeypatch.setattr(
        "mq_agent.memory.codegraph_runtime.shutil.which",
        forbidden_which,
    )

    result = search_codegraph("query", tmp_path)

    assert result["ok"] is False
    assert "index is unavailable" in result["reason"]
