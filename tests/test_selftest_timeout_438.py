"""#438: a delegated `mqlaunch selftest` must get its real runtime, and a
timeout must read as a timeout.

`mqlaunch selftest` takes ~126 s. mq-mcp now allows it 300 s and reports a
timeout as `[exit 124 (timed out)]`. The bridge's HTTP deadline and the
runner's step deadline must sit above that, so the innermost limit fires first
and its message reaches the run record.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from mq_agent.tools.mcp_bridge import MCPBridge
from mq_agent.workflows import Runner, new_run
from mq_agent.workflows.evaluator import normalize_result
from mq_agent.workflows.models import StepStatus
from mq_agent.workflows.runner import DEFAULT_STEP_TIMEOUT
from mq_agent.workflows.storage import WorkflowStore

from tests.test_workflow_runner import FakeExecutor, _plan, _provider, _step

#: mq-mcp's MQLAUNCH_SELFTEST_TIMEOUT.
MQ_MCP_SELFTEST_LIMIT = 300


def _recording(seen: list[float]):
    def result(timeout: float) -> dict:
        seen.append(timeout)
        return {"ok": True}
    return result


def _mcp_text(text: str) -> list:
    return [{"type": "text", "text": text}]


def test_selftest_http_deadline_clears_mq_mcp_limit():
    with patch("httpx.post", return_value=MagicMock()) as post:
        MCPBridge().call_tool("run_mqlaunch_selftest", {})
    assert post.call_args.kwargs["timeout"] > MQ_MCP_SELFTEST_LIMIT


def test_selftest_step_deadline_clears_http_deadline(tmp_path):
    with patch("httpx.post", return_value=MagicMock()) as post:
        MCPBridge().call_tool("run_mqlaunch_selftest", {})
    http_deadline = post.call_args.kwargs["timeout"]

    seen: list[float] = []
    runner = Runner(WorkflowStore(tmp_path), FakeExecutor(), policy_provider=_provider())
    run = new_run(_plan([_step("selftest", "run_mqlaunch_selftest")]))
    with patch("mq_agent.workflows.runner.ThreadPoolExecutor") as pool_cls:
        future = pool_cls.return_value.__enter__.return_value.submit.return_value
        future.result.side_effect = _recording(seen)
        runner.run(run)
    assert seen and seen[0] > http_deadline


def test_other_steps_keep_the_default_deadline(tmp_path):
    seen: list[float] = []
    runner = Runner(WorkflowStore(tmp_path), FakeExecutor(), policy_provider=_provider())
    run = new_run(_plan([_step("doctor", "run_mqlaunch_doctor")]))
    with patch("mq_agent.workflows.runner.ThreadPoolExecutor") as pool_cls:
        future = pool_cls.return_value.__enter__.return_value.submit.return_value
        future.result.side_effect = _recording(seen)
        runner.run(run)
    assert seen == [DEFAULT_STEP_TIMEOUT]


def test_exit_124_is_timeout_not_fail():
    result = normalize_result(_mcp_text(
        "mqlaunch selftest [exit 124 (timed out)]\n\nERROR: mqlaunch selftest timed out after 300s."
    ))
    assert result["ok"] is False
    assert result["code"] == "TIMEOUT"
    assert "timed out after 300s" in result["data"]["text"]


def test_exit_1_stays_fail():
    result = normalize_result(_mcp_text("mqlaunch selftest [exit 1 (failures)]\n\n[FAIL] lint"))
    assert result["ok"] is False
    assert result["code"] == "FAIL"


def test_selftest_timeout_is_persisted_and_retrievable(tmp_path):
    store = WorkflowStore(tmp_path)
    timed_out = _mcp_text(
        "mqlaunch selftest [exit 124 (timed out)]\n\nERROR: mqlaunch selftest timed out after 300s."
    )
    ex = FakeExecutor(results={"run_mqlaunch_selftest": timed_out})
    run = new_run(_plan([_step("selftest", "run_mqlaunch_selftest")]))
    Runner(store, ex, policy_provider=_provider()).run(run)

    loaded = store.load_run(run.plan.run_id)
    step = loaded.plan.steps[0]
    assert step.status is StepStatus.FAILED
    assert step.result is not None
    assert step.result["code"] == "TIMEOUT"
    assert "timed out after 300s" in step.result["data"]["text"]


# --- #440: long output keeps its end, where failures are ----------------------


def test_long_output_keeps_the_failing_tail():
    from mq_agent.workflows.evaluator import _MAX_TEXT_LEN

    head = "mqlaunch selftest [exit 2 (failures)]\n\n"
    filler = "".join(f"  ok: check {i}\n" for i in range(5000))
    tail = "ERROR: OPENAI_API_KEY is already exported in this shell."
    result = normalize_result(_mcp_text(head + filler + tail))
    kept = result["data"]["text"]
    assert result["code"] == "FAIL"
    assert kept.startswith("mqlaunch selftest [exit 2")
    assert kept.endswith(tail)
    assert "middle omitted" in kept
    assert len(kept) <= _MAX_TEXT_LEN


def test_short_output_is_kept_whole():
    text = "mqlaunch doctor [exit 0 (healthy)]\n\nall good"
    assert normalize_result(_mcp_text(text))["data"]["text"] == text
