"""mq-agent workflow orchestration package.

Phase 1 (this PR) ships the **workflow contract only**: schema, data models and
validation. There is intentionally no runner, no tool execution, no state
storage, no approvals and no adaptive planning here yet — those land in later
phases (see ``docs/roadmap-workflow-orchestration.md``).

Ownership boundary this package sits inside:

    mqlaunch   = operator surface
    mq-agent   = orchestration   <-- this package
    mq-mcp     = execution
    mqobsidian = observations and learning
"""
from __future__ import annotations

from .models import (
    DEFAULT_MAX_STEPS,
    FORBIDDEN_TOOLS,
    MAX_STEPS_HARD_CAP,
    SCHEMA_ID,
    StepApproval,
    StepCondition,
    StepStatus,
    WorkflowPlan,
    WorkflowStatus,
    WorkflowStep,
    validate_plan,
)

__all__ = [
    "DEFAULT_MAX_STEPS",
    "FORBIDDEN_TOOLS",
    "MAX_STEPS_HARD_CAP",
    "SCHEMA_ID",
    "StepApproval",
    "StepCondition",
    "StepStatus",
    "WorkflowPlan",
    "WorkflowStatus",
    "WorkflowStep",
    "validate_plan",
]
