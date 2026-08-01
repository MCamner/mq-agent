"""`run-tool` must exit non-zero when the tool did not succeed.

Found from the operator end: `mqlaunch repo-health` printed
"repo_signal_analyze failed: Blocked path outside allowed roots" and exited 0.
The shell was innocent — mqlaunch's arm and mq-agent-menu's `_run_agent_repo_health`
both preserve the status with `|| return $?`. `run-tool` itself printed the
result and returned implicitly, so every failure below it arrived as success.

Two classes have to fail, and neither carries a flag to check:

* mq-mcp reports a tool failure as the *string* ``"<tool> failed: <exc>"``.
  There is no ``isError`` anywhere in server.py — that convention is the whole
  signal, and it is used consistently (``repo_signal_analyze failed:``,
  ``update_repo_file failed:``, ``Command failed:``).
* MCPBridge.call_tool returns transport problems as strings too, so an
  unreachable server, an HTTP error and a missing tool all looked like output.

`memory ingest` in the same file already does `typer.Exit(0 if status == "OK"
else 1)`. This brings run-tool to the same standard.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from mq_agent.main import app

runner = CliRunner()

TOOL = "repo_signal_analyze"


def _run(result, *extra):
    """Invoke run-tool with the bridge fully stubbed.

    describe_tool is stubbed too, and that is not incidental. It reaches the
    server for a tool's safety class and falls back to name classification when
    there is none; an unknown class makes run-tool exit 1 at the safety gate,
    before the result is ever read. With a local mq-mcp running, these tests
    passed while CI failed all three exit-zero cases — the assertions were
    measuring whether a server happened to be up. Everything the command talks
    to is stubbed now, so the test measures the exit-code contract only.
    """
    from mq_agent.tools.mcp_registry import MCPSafetyClass, MCPToolSpec

    # READ_ONLY explicitly, not from_name(). The name heuristic classifies
    # repo_signal_analyze as UNKNOWN — there is no `repo_` or `_analyze` rule —
    # and UNKNOWN is refused at the safety gate before the result is read. A
    # server supplies the real class from the tool contract, which is why this
    # only showed up once CI ran it without one.
    spec = MCPToolSpec.from_name(TOOL)
    spec.safety_class = MCPSafetyClass.READ_ONLY
    spec.read_only = True
    spec.source = "mq-mcp"

    with patch("mq_agent.tools.mcp_bridge.MultiMCPBridge.call_tool", return_value=result), \
         patch("mq_agent.tools.mcp_bridge.MultiMCPBridge.describe_tool", return_value=spec), \
         patch("mq_agent.tools.mcp_bridge.MultiMCPBridge.is_available", return_value=True):
        return runner.invoke(app, ["run-tool", TOOL, *extra])


def test_success_exits_zero():
    assert _run({"ok": True, "score": 91}).exit_code == 0


def test_tool_failure_string_exits_non_zero():
    # The exact shape mq-mcp returned for the reported bug.
    failure = f"{TOOL} failed: Blocked path outside allowed roots: /Users/x"
    assert _run(failure).exit_code != 0


def test_tool_failure_nested_in_content_exits_non_zero():
    # What actually came back over the wire: the failure text is buried in an
    # MCP content list, not at the top level. A check that only looked at
    # `isinstance(result, str)` would have passed this one — and this is the
    # shape the operator hit.
    payload = [
        [{"annotations": None, "meta": None,
          "text": f"{TOOL} failed: Blocked path outside allowed roots: /Users/x",
          "type": "text"}],
        {"result": f"{TOOL} failed: Blocked path outside allowed roots: /Users/x"},
    ]
    assert _run(payload).exit_code != 0


def test_unreachable_server_exits_non_zero():
    assert _run("mq-mcp not reachable at http://localhost:8765").exit_code != 0


def test_http_error_exits_non_zero():
    assert _run("mq-mcp error 500: internal error").exit_code != 0


def test_bridge_exception_exits_non_zero():
    assert _run("MCP bridge error: connection reset").exit_code != 0


def test_missing_tool_exits_non_zero():
    assert _run(f"Tool '{TOOL}' not found on any connected MCP server.").exit_code != 0


def test_json_mode_fails_too_and_stays_parseable():
    # A caller that asked for JSON still needs the document; the status is what
    # tells it the run failed. Printing valid JSON and exiting 0 would make the
    # failure invisible to exactly the consumer that cannot read a panel.
    failure = f"{TOOL} failed: Blocked path outside allowed roots: /Users/x"
    result = _run(failure, "--json")
    assert result.exit_code != 0
    assert json.loads(result.stdout)["result"] == failure


def test_success_word_in_output_is_not_a_failure():
    # "failed" has to appear as the tool's own verdict, not anywhere in the
    # payload. A report that counts failures is a successful report.
    payload = {"summary": "0 failed, 12 passed", "status": "ok"}
    assert _run(payload).exit_code == 0
