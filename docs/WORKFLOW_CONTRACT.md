# MQ Workflow Contract (v1)

**Version:** 1.0
**Phase:** 1 — Workflow contract
**Status:** Active (shape only — no execution)
**Schema id:** `mq-workflow-plan.v1`

> Not to be confused with [`B2_WORKFLOW_CONTRACT.md`](B2_WORKFLOW_CONTRACT.md),
> which describes the B2 prompt-OS pipeline. This document defines the **generic
> multi-step workflow plan** used by the workflow orchestration engine described
> in [`roadmap-workflow-orchestration.md`](roadmap-workflow-orchestration.md).

---

## Purpose

This contract locks the **shape** of a workflow plan before any runner or tool
execution exists. It is the highest-leverage artifact in the orchestration
roadmap: if the state machine or runner were built before this contract, the
implementation would define the architecture by accident, and later safety rules
would become corrections instead of foundations.

A workflow plan describes **intended structure**. It is *not* the truth about
live runtime. Per the repo source-of-truth rule, anything depending on current
code, tests, or CLI behavior must be verified against the repo, not a plan file.

This PR ships shape only. It contains:

- `schemas/workflow-plan.v1.json` — declarative JSON Schema artifact
- `mq_agent/workflows/models.py` — enforced pydantic models + validation
- `mq_agent/workflows/__init__.py` — package surface
- `docs/WORKFLOW_CONTRACT.md` — this document
- `tests/test_workflow_contract.py` — contract tests

It deliberately contains **no** runner, tool execution, state storage,
approvals, mqlaunch routing, Bridget changes, or adaptive planning.

---

## Ownership boundary

```
mqlaunch   = operator surface
mq-agent   = orchestration          <-- this contract lives here
mq-mcp     = execution
mqobsidian = observations and learning
```

No planning logic in `mqlaunch`. No general workflow state in Bridget. No
execution in `mqobsidian`. See the merged architecture decision in mqobsidian
PR #23 (`docs/command-learning-system.md`) for the learning side.

---

## Two-layer enforcement

| Layer | File | Enforces |
|-------|------|----------|
| Declarative | `schemas/workflow-plan.v1.json` | field shape, types, enums, `additionalProperties: false`, `maxItems`, `shell_exec` exclusion |
| Enforced | `mq_agent/workflows/models.py` | everything above **plus** cross-reference and graph rules JSON Schema cannot express |

JSON Schema cannot express "this id is unique", "this dependency exists", or
"this graph is acyclic". Those live in the pydantic `model_validator`. Both
layers are tested. **`validate_plan(data)` is the single entry point** callers
should use; it raises `pydantic.ValidationError` on any violation and touches
neither the filesystem nor any tool.

> **Contract decision:** the models use **pydantic v2** (the repo's declared
> validation dependency) rather than the `dataclass`/`StrEnum` style used in
> `mq_agent/core/state.py`, because `extra="forbid"`, field validators, and a
> cross-field `model_validator` map directly onto the v1 requirements (unknown-
> field rejection, cycle detection). Status enums still use `StrEnum` to match
> the repo idiom.

---

## Workflow plan

Minimal valid plan:

```json
{
  "schema": "mq-workflow-plan.v1",
  "run_id": "run_20260626_001",
  "template": "repo-preflight",
  "task": "Verify repository readiness",
  "repo": "/Users/mansys/macos-scripts",
  "status": "planned",
  "current_step": null,
  "max_steps": 6,
  "max_replans": 0,
  "steps": []
}
```

### Workflow fields

| Field | Type | Rules |
|-------|------|-------|
| `schema` | string | must equal `mq-workflow-plan.v1` |
| `run_id` | string | non-empty |
| `template` | string | non-empty |
| `task` | string | non-empty |
| `repo` | string | non-empty |
| `status` | enum | one of the workflow statuses below |
| `current_step` | string \| null | if set, must reference an existing step id |
| `max_steps` | int | `1..10`, default `6` |
| `max_replans` | int | must be `0` in v1 |
| `steps` | array | `<= 10` items, `<= max_steps` items |

Timestamps (`created_at`, `updated_at`) are **not** part of the plan contract —
they belong to workflow state (Phase 2), which is a separate concern from the
plan shape.

### Workflow statuses

```
planned
awaiting_approval
running
paused
failed
cancelled
completed
```

---

## Step

```json
{
  "id": "s1",
  "name": "Run mqlaunch doctor",
  "tool": "run_mqlaunch_doctor",
  "args": {},
  "depends_on": [],
  "condition": "always",
  "approval": "none",
  "status": "pending",
  "attempt": 0,
  "result": null,
  "error": null
}
```

### Step fields

| Field | Type | Rules |
|-------|------|-------|
| `id` | string | non-empty, unique within plan |
| `name` | string | non-empty |
| `tool` | string | non-empty, never `shell_exec` |
| `args` | object | tool arguments |
| `depends_on` | array | unique ids, each must exist, no self-reference |
| `condition` | enum | `always` (default) or `all_deps_passed` |
| `approval` | enum | `none` (default), `plan`, `step`, `forbidden` |
| `status` | enum | one of the step statuses below |
| `attempt` | int | `>= 0`, default `0` |
| `result` | object \| null | normalized result (later phases) |
| `error` | string \| null | error summary |

### Step statuses

```
pending
blocked
awaiting_approval
running
passed
failed
skipped
cancelled
```

### Approval levels (defined now, enforced in Phase 5/6)

| Level | Meaning |
|-------|---------|
| `none` | read-only, no subprocess, no external side effects |
| `plan` | read-only subprocess / test run; whole plan approved once |
| `step` | mutation (file write, network, external app); approve each step |
| `forbidden` | push, release, recursive workflow start, unknown shell exec — not in v1 |

---

## v1 invariants (locked here)

- `schema` == `mq-workflow-plan.v1`
- unknown fields are rejected (top-level and per-step)
- step ids are unique
- `depends_on` references only existing steps; no self-reference
- the dependency graph is acyclic
- `1 <= max_steps <= 10`, default `6`
- `len(steps) <= max_steps` and `len(steps) <= 10`
- `max_replans == 0`
- `tool` is non-empty and never `shell_exec`

---

## Why these constraints

| Constraint | Risk it closes |
|------------|----------------|
| no `shell_exec` | a single composed shell string (`git status && pytest && git push`) masquerading as one step; every side effect must be its own typed tool step |
| `max_replans == 0` | the model freely recombining tool chains; v1 is fixed templates only |
| `max_steps <= 10` | runaway plans |
| acyclic + dependency existence | non-terminating or undefined execution order |
| `extra="forbid"` | silent contract drift via unrecognized fields |
| plan ≠ runtime truth | treating a stored plan as the current state of the repo or tools |

---

## Out of scope for this contract

Runner, evaluator, conditions engine, state persistence, approval prompts,
policy gates, mqlaunch routing, Bridget delegation, workflow observations, and
adaptive planning. See the phase roadmap for where each lands.
