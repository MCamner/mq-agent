"""Tests for stack sweep summary classification."""

from mq_agent.main import _stack_sweep_status


def test_sweep_ready_requires_full_publish_score() -> None:
    assert _stack_sweep_status(100, 16, 16) == ("green", "✓ ready")
    assert _stack_sweep_status(90, 13, 16) == ("yellow", "~ publish")


def test_sweep_status_distinguishes_review_from_weak() -> None:
    assert _stack_sweep_status(70, 11, 16) == ("yellow", "~ review")
    assert _stack_sweep_status(40, 8, 16) == ("red", "✗ weak")
