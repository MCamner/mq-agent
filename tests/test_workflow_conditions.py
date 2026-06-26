"""Condition and result-normalization tests (Phase 4). Pure, no execution."""
from __future__ import annotations

from mq_agent.workflows import SCHEMA_ID, conditions, normalize_result, validate_plan


def _step(step_id, *, condition="always", status="pending", depends_on=None):
    return {
        "id": step_id,
        "name": f"Step {step_id}",
        "tool": "run_mqlaunch_doctor",
        "args": {},
        "depends_on": depends_on or [],
        "condition": condition,
        "approval": "none",
        "status": status,
        "attempt": 0,
        "result": None,
        "error": None,
    }


def _plan(steps):
    return validate_plan(
        {
            "schema": SCHEMA_ID,
            "run_id": "run_x",
            "template": "t",
            "task": "t",
            "repo": "/tmp/x",
            "status": "running",
            "current_step": None,
            "max_steps": 6,
            "max_replans": 0,
            "steps": steps,
        }
    )


# --- conditions ------------------------------------------------------------


def test_always_condition_is_true():
    plan = _plan([_step("s1", condition="always")])
    assert conditions.evaluate(plan.steps[0], plan) is True


def test_all_deps_passed_true_when_deps_passed():
    plan = _plan([_step("s1", status="passed"), _step("s2", condition="all_deps_passed", depends_on=["s1"])])
    assert conditions.evaluate(plan.steps[1], plan) is True


def test_all_deps_passed_false_when_dep_failed():
    plan = _plan([_step("s1", status="failed"), _step("s2", condition="all_deps_passed", depends_on=["s1"])])
    assert conditions.evaluate(plan.steps[1], plan) is False


def test_all_deps_passed_false_when_dep_skipped():
    plan = _plan([_step("s1", status="skipped"), _step("s2", condition="all_deps_passed", depends_on=["s1"])])
    assert conditions.evaluate(plan.steps[1], plan) is False


# --- normalization ---------------------------------------------------------


def test_normalize_timeout():
    out = normalize_result(None, timed_out=True)
    assert out["ok"] is False and out["code"] == "TIMEOUT"


def test_normalize_exception():
    out = normalize_result(None, error=RuntimeError("boom"))
    assert out["ok"] is False and out["code"] == "ERROR"
    assert "boom" in out["summary"]


def test_normalize_bridge_error_string():
    out = normalize_result("mq-mcp is not reachable")
    assert out["ok"] is False and out["code"] == "ERROR"


def test_normalize_explicit_ok_true():
    out = normalize_result({"ok": True, "summary": "Selftest passed"})
    assert out["ok"] is True and out["code"] == "PASS"
    assert out["summary"] == "Selftest passed"


def test_normalize_explicit_ok_false():
    out = normalize_result({"ok": False, "message": "doctor found issues"})
    assert out["ok"] is False and out["code"] == "FAIL"
    assert out["summary"] == "doctor found issues"


def test_normalize_returncode_zero_is_pass():
    assert normalize_result({"returncode": 0})["ok"] is True


def test_normalize_returncode_nonzero_is_fail():
    assert normalize_result({"exit_code": 2})["ok"] is False


def test_normalize_status_word():
    assert normalize_result({"status": "PASS"})["ok"] is True
    assert normalize_result({"status": "failed"})["ok"] is False


def test_normalize_redacts_secrets_in_data():
    out = normalize_result({"ok": True, "api_key": "sk-LEAK"})
    assert out["data"]["api_key"] == "***redacted***"


# --- MCP content-block envelope (real mq-mcp shape) ------------------------


def _mcp(text):
    # mq-mcp returns nested content blocks like [[{"type":"text","text":...}]]
    return [[{"type": "text", "text": text}]]


def test_normalize_mcp_envelope_exit_zero_is_pass():
    out = normalize_result(_mcp("mqlaunch doctor [exit 0 (healthy)]\n\nMQ DOCTOR\n..."))
    assert out["ok"] is True and out["code"] == "PASS"
    assert out["summary"] == "mqlaunch doctor [exit 0 (healthy)]"
    assert "MQ DOCTOR" in out["data"]["text"]


def test_normalize_mcp_envelope_nonzero_exit_is_fail():
    out = normalize_result(_mcp("mqlaunch selftest [exit 1 (failures)]\n[FAIL] something"))
    assert out["ok"] is False and out["code"] == "FAIL"
    assert out["summary"].startswith("mqlaunch selftest [exit 1")


def test_normalize_mcp_envelope_long_text_is_bounded():
    out = normalize_result(_mcp("header [exit 0]\n" + "x" * 5000))
    assert len(out["data"]["text"]) <= 2000
    assert len(out["summary"]) <= 280
