"""Tests for mq_agent core layer (no OpenAI calls)."""

from mq_agent.core.executor import Executor
from mq_agent.core.memory import Memory
from mq_agent.core.safety import SafetyGate
from mq_agent.core.state import AgentState, PlanStep, SafetyMode, StepStatus

# ── state ──────────────────────────────────────────────────────────────────

def test_state_is_complete_when_all_steps_done():
    state = AgentState(goal="test")
    state.plan = [
        PlanStep(index=0, description="a", status=StepStatus.SUCCESS),
        PlanStep(index=1, description="b", status=StepStatus.SKIPPED),
    ]
    assert state.is_complete

def test_state_not_complete_with_pending_step():
    state = AgentState(goal="test")
    state.plan = [
        PlanStep(index=0, description="a", status=StepStatus.SUCCESS),
        PlanStep(index=1, description="b", status=StepStatus.PENDING),
    ]
    assert not state.is_complete

def test_state_has_failures():
    state = AgentState(goal="test")
    state.plan = [PlanStep(index=0, description="a", status=StepStatus.FAILED)]
    assert state.has_failures

def test_state_to_dict():
    state = AgentState(goal="my goal")
    d = state.to_dict()
    assert d["goal"] == "my goal"
    assert d["steps"] == []


# ── safety ─────────────────────────────────────────────────────────────────

def test_read_only_blocks_run_command():
    gate = SafetyGate(SafetyMode.READ_ONLY)
    step = PlanStep(index=0, description="Run tests", tool="run_command")
    allowed, reason = gate.check(step)
    assert not allowed
    assert "not permitted" in reason

def test_read_only_allows_git_status():
    gate = SafetyGate(SafetyMode.READ_ONLY)
    step = PlanStep(index=0, description="Check status", tool="git_status")
    allowed, _ = gate.check(step)
    assert allowed

def test_suggest_blocks_all():
    gate = SafetyGate(SafetyMode.SUGGEST)
    step = PlanStep(index=0, description="Read file", tool="read_file")
    allowed, reason = gate.check(step)
    assert not allowed
    assert "Suggest mode" in reason

def test_execute_blocks_destructive():
    gate = SafetyGate(SafetyMode.EXECUTE)
    step = PlanStep(index=0, description="Force push to main", tool="run_command")
    allowed, reason = gate.check(step)
    assert not allowed
    assert "--approve" in reason

def test_execute_allows_safe():
    gate = SafetyGate(SafetyMode.EXECUTE)
    step = PlanStep(index=0, description="Run test suite", tool="run_command")
    allowed, _ = gate.check(step)
    assert allowed

def test_dangerous_allows_everything():
    gate = SafetyGate(SafetyMode.DANGEROUS)
    step = PlanStep(index=0, description="Force push to main", tool="run_command")
    allowed, _ = gate.check(step)
    assert allowed


# ── executor ───────────────────────────────────────────────────────────────

def _mock_registry():
    return {
        "echo_tool": lambda message="hello": f"echo: {message}",
        "failing_tool": lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    }

def test_executor_dry_run_skips_actual_call():
    gate = SafetyGate(SafetyMode.EXECUTE)
    ex = Executor(gate, _mock_registry(), dry_run=True)
    state = AgentState(goal="test", safety_mode=SafetyMode.EXECUTE)
    step = PlanStep(index=0, description="Echo something", tool="echo_tool")
    result = ex.run_step(step, state)
    assert result.status == StepStatus.SUCCESS
    assert "[dry-run]" in result.result

def test_executor_runs_tool():
    gate = SafetyGate(SafetyMode.EXECUTE)
    ex = Executor(gate, _mock_registry(), dry_run=False)
    state = AgentState(goal="test", safety_mode=SafetyMode.EXECUTE)
    step = PlanStep(index=0, description="Echo something", tool="echo_tool", args={"message": "hi"})
    result = ex.run_step(step, state)
    assert result.status == StepStatus.SUCCESS
    assert "echo: hi" in result.result

def test_executor_captures_tool_failure():
    gate = SafetyGate(SafetyMode.EXECUTE)
    ex = Executor(gate, _mock_registry(), dry_run=False)
    state = AgentState(goal="test", safety_mode=SafetyMode.EXECUTE)
    step = PlanStep(index=0, description="Failing step", tool="failing_tool")
    result = ex.run_step(step, state)
    assert result.status == StepStatus.FAILED
    assert "boom" in result.error

def test_executor_unknown_tool():
    gate = SafetyGate(SafetyMode.EXECUTE)
    ex = Executor(gate, _mock_registry(), dry_run=False)
    state = AgentState(goal="test", safety_mode=SafetyMode.EXECUTE)
    step = PlanStep(index=0, description="Run unknown", tool="nonexistent_tool")
    result = ex.run_step(step, state)
    assert result.status == StepStatus.FAILED
    assert "Unknown tool" in result.error

def test_executor_skips_when_safety_blocks():
    gate = SafetyGate(SafetyMode.SUGGEST)
    ex = Executor(gate, _mock_registry(), dry_run=False)
    state = AgentState(goal="test", safety_mode=SafetyMode.SUGGEST)
    step = PlanStep(index=0, description="Read file", tool="echo_tool")
    result = ex.run_step(step, state)
    assert result.status == StepStatus.SKIPPED


# ── memory ─────────────────────────────────────────────────────────────────

def test_memory_session_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("mq_agent.core.memory.MEMORY_DIR", tmp_path)
    monkeypatch.setattr("mq_agent.core.memory.PERSISTENT_FILE", tmp_path / "memory.json")
    mem = Memory()
    mem.set("foo", "bar")
    assert mem.get("foo") == "bar"

def test_memory_persistent_survives_reload(tmp_path, monkeypatch):
    monkeypatch.setattr("mq_agent.core.memory.MEMORY_DIR", tmp_path)
    monkeypatch.setattr("mq_agent.core.memory.PERSISTENT_FILE", tmp_path / "memory.json")
    mem1 = Memory()
    mem1.set("key", "value", persistent=True)
    mem2 = Memory()
    assert mem2.get("key") == "value"

def test_memory_session_overrides_persistent(tmp_path, monkeypatch):
    monkeypatch.setattr("mq_agent.core.memory.MEMORY_DIR", tmp_path)
    monkeypatch.setattr("mq_agent.core.memory.PERSISTENT_FILE", tmp_path / "memory.json")
    mem = Memory()
    mem.set("k", "persistent", persistent=True)
    mem.set("k", "session")
    assert mem.get("k") == "session"
