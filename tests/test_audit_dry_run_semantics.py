"""Audit dry-run must not produce verified evidence or persistent memory."""

from unittest.mock import MagicMock, patch

from mq_agent.agents.audit_agent import AuditAgent


def _agent():
    agent = AuditAgent.__new__(AuditAgent)
    agent.client = MagicMock()
    agent.planner = MagicMock()
    agent.planner.create_plan.return_value = []
    agent.verifier = MagicMock()
    agent.verifier.verify_plan.return_value = {
        "all_passed": True,
        "failures": [],
    }
    return agent


def test_dry_run_does_not_verify_or_persist():
    agent = _agent()

    with (
        patch(
            "mq_agent.agents.audit_agent.repo_summary",
            return_value="test",
        ),
        patch(
            "mq_agent.core.memory.Memory",
        autospec=True,
        ) as memory_cls,
        patch(
            "mq_agent.agents.audit_agent.Executor",
        ) as executor_cls,
    ):
        result = agent.run(".", dry_run=True)

    assert result["dry_run"] is True
    assert result["passed"] is False
    assert result["verification"]["status"] == "not_verified"

    agent.verifier.verify_plan.assert_not_called()
    memory_cls.return_value.set.assert_not_called()
    executor_cls.return_value.run_plan.assert_called_once()


def test_normal_audit_still_verifies_and_persists():
    agent = _agent()

    with (
        patch(
            "mq_agent.agents.audit_agent.repo_summary",
            return_value="test",
        ),
        patch(
            "mq_agent.core.memory.Memory",
            autospec=True,
        ) as memory_cls,
        patch(
            "mq_agent.agents.audit_agent.Executor",
        ),
    ):
        result = agent.run(".", dry_run=False)

    assert result["dry_run"] is False
    assert result["passed"] is True

    agent.verifier.verify_plan.assert_called_once()
    memory_cls.return_value.set.assert_called_once()
