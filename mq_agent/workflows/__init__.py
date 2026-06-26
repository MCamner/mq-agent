"""mq-agent workflow orchestration package.

Phase 1 ships the **workflow contract**: schema, data models and validation.
Phase 2 adds **local workflow state**: the ``WorkflowRun`` envelope, pure state
transitions (pause/resume/cancel, dead-process reconciliation, sanitization) and
filesystem persistence (``WorkflowStore``). There is intentionally still no
runner, no tool execution, no approvals and no adaptive planning here — those
land in later phases (see ``docs/roadmap-workflow-orchestration.md``).

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
from .state import (
    WorkflowRun,
    WorkflowStateError,
    cancel,
    new_run,
    pause,
    reconcile_dead_process,
    resume,
    sanitize_result,
    sanitize_run,
    touch,
)
from .storage import WorkflowStore, default_workflows_dir
from .templates import (
    ALLOWED_TOOLS,
    TemplateError,
    instantiate,
    list_templates,
    load_template,
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
    # Phase 2 — state
    "WorkflowRun",
    "WorkflowStateError",
    "new_run",
    "touch",
    "pause",
    "resume",
    "cancel",
    "reconcile_dead_process",
    "sanitize_result",
    "sanitize_run",
    # Phase 2 — storage
    "WorkflowStore",
    "default_workflows_dir",
    # Phase 3 — templates
    "ALLOWED_TOOLS",
    "TemplateError",
    "instantiate",
    "list_templates",
    "load_template",
]
