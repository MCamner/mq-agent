"""Verification bounds text without inventing runtime truncation."""
from __future__ import annotations

import json
from types import SimpleNamespace

from mq_agent.core.executor import Executor
from mq_agent.core.safety import SafetyGate, SafetyMode
from mq_agent.core.state import AgentState, PlanStep, StepStatus
from mq_agent.core.tool_contract import produces
from mq_agent.core.verification import Verifier


class _CapturingClient:
    def __init__(self, response: dict | None = None):
        self.response = response or {"success": True, "reason": "complete"}
        self.sent: dict = {}
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.sent = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(self.response))
                )
            ]
        )


@produces("paths")
def _nineteen() -> str:
    return "\n".join(f"file-{index}.py" for index in range(19))


def _long_reader(path: str) -> str:
    return f"{path}:" + ("x" * 300)


def test_complete_fan_out_with_bounded_excerpt_is_not_runtime_truncation() -> None:
    source = PlanStep(index=0, description="find", tool="find")
    read = PlanStep(
        index=1,
        description="read all",
        tool="read",
        for_each={"step": 0, "as": "path"},
    )
    state = AgentState(goal="audit", safety_mode=SafetyMode.DANGEROUS)
    state.plan = [source, read]
    executor = Executor(
        SafetyGate(SafetyMode.DANGEROUS),
        {"find": _nineteen, "read": _long_reader},
    )
    executor.run_plan(state)
    assert len(str(read.result)) > 4000

    client = _CapturingClient()
    verifier = Verifier.__new__(Verifier)
    verifier.client = client  # type: ignore[assignment]
    verifier._model = "test-model"
    verifier._system_prompt = "test"

    passed, _ = verifier.verify(read)

    payload = json.loads(client.sent["messages"][1]["content"])
    assert passed is True
    assert payload["result_excerpt_truncated"] is True
    assert len(payload["result_excerpt"]) == 4000
    assert payload["fan_out"] == {
        "source_item_count": 19,
        "executed_call_count": 19,
        "complete": True,
    }


def test_incomplete_fan_out_fails_from_executor_metadata_without_model() -> None:
    client = _CapturingClient()
    verifier = Verifier.__new__(Verifier)
    verifier.client = client  # type: ignore[assignment]
    verifier._model = "test-model"
    verifier._system_prompt = "test"
    step = PlanStep(
        index=1,
        description="read capped collection",
        tool="read_file",
        status=StepStatus.SUCCESS,
        source_item_count=43,
        executed_call_count=25,
        fan_out_complete=False,
    )

    passed, reason = verifier.verify(step)

    assert passed is False
    assert "25 of 43" in reason
    assert client.sent == {}
