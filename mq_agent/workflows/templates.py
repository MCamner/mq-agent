"""Fixed workflow templates (Phase 3).

Three bounded, read-only templates ship as JSON skeletons in ``templates/``:

  * ``repo-preflight``   — doctor → selftest → release-check
  * ``review-and-test``  — git diff → review (advisory) → run tests
  * ``release-ready``    — status → repo-signal → selftest → release-check

A template is *not* a runnable plan: it omits the run-specific envelope fields
(``run_id``, ``repo``). ``instantiate(name, repo, run_id)`` fills those in, lets
the pydantic models supply per-step defaults, and validates the result against
the v1 contract — so every instantiated plan is a valid ``mq-workflow-plan.v1``.

v1 templates are fixed: no free shell, no mutation, clear stop conditions
(``depends_on`` + ``all_deps_passed``), and every tool must appear in the
temporary static allowlist below. That allowlist is replaced by machine-readable
tool policy from mq-mcp in Phase 5; until then it is the safety boundary.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import DEFAULT_MAX_STEPS, SCHEMA_ID, WorkflowPlan, validate_plan

TEMPLATES_DIR = Path(__file__).parent / "templates"

#: Temporary static allowlist of tool names a v1 workflow may use. Every tool
#: is read-only (no file writes, no push/release). Replaced by mq-mcp tool
#: policy (Phase 5). ``shell_exec`` is intentionally absent.
ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "git_status",
        "git_diff",
        "review_diff",
        "run_tests",
        "repo_signal_status",
        "run_mqlaunch_doctor",
        "run_mqlaunch_selftest",
        "run_mqlaunch_release_check",
    }
)


class TemplateError(Exception):
    """Raised for an unknown template or a template that violates v1 limits."""


def list_templates() -> list[str]:
    """Return the sorted names of available templates."""
    return sorted(p.stem for p in TEMPLATES_DIR.glob("*.json"))


def load_template(name: str) -> dict:
    """Load a raw template definition by name."""
    path = TEMPLATES_DIR / f"{name}.json"
    if not path.exists():
        known = ", ".join(list_templates()) or "(none)"
        raise TemplateError(f"unknown template {name!r}; known templates: {known}")
    return json.loads(path.read_text(encoding="utf-8"))


def _check_tools(steps: list[dict]) -> None:
    used = {step.get("tool", "") for step in steps}
    unknown = sorted(t for t in used if t not in ALLOWED_TOOLS)
    if unknown:
        raise TemplateError(
            "template uses tools not in the workflow allowlist: "
            + ", ".join(unknown)
        )


def instantiate(name: str, repo: str, run_id: str, *, max_replans: int = 0) -> WorkflowPlan:
    """Build a validated ``WorkflowPlan`` from a template for ``repo``.

    Does not persist or execute anything. Raises ``TemplateError`` for an
    unknown template or a disallowed tool, and ``pydantic.ValidationError`` if
    the resulting plan violates the v1 contract.

    ``max_replans`` defaults to 0 (non-adaptive). A caller may opt a run into
    Phase 10 limited adaptive planning by passing ``max_replans=1``; the value
    is capped at 1 by the plan contract.
    """
    raw = load_template(name)
    steps = raw["steps"]
    _check_tools(steps)
    plan = {
        "schema": SCHEMA_ID,
        "run_id": run_id,
        "template": raw["template"],
        "task": raw["task"],
        "repo": repo,
        "status": "planned",
        "current_step": None,
        "max_steps": raw.get("max_steps", DEFAULT_MAX_STEPS),
        "max_replans": max_replans,
        "steps": steps,
    }
    return validate_plan(plan)
