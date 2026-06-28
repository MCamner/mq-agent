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
from . import conditions
from .evaluator import normalize_result
from .policy import PolicyDecision, PolicyProvider, diff_policies
from .runner import (
    DEFAULT_STEP_TIMEOUT,
    RUNNER_MAX_STEPS,
    MCPBridgeExecutor,
    Runner,
)
from .adapter import (
    DIAGNOSTIC_TOOLS,
    DefaultReplanner,
    ReplanDecision,
    ReplanMove,
    ReplanProposal,
    Replanner,
    apply_replan,
    validate_replan,
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
    # Phase 4 — runner
    "conditions",
    "normalize_result",
    "Runner",
    "MCPBridgeExecutor",
    "RUNNER_MAX_STEPS",
    "DEFAULT_STEP_TIMEOUT",
    # Phase 6 — policy gates
    "PolicyProvider",
    "PolicyDecision",
    "diff_policies",
    # Phase 10 — limited adaptive planning
    "DIAGNOSTIC_TOOLS",
    "DefaultReplanner",
    "ReplanDecision",
    "ReplanMove",
    "ReplanProposal",
    "Replanner",
    "apply_replan",
    "validate_replan",
]
