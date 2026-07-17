# Roadmap: Multi-step Workflow Orchestration

**Status:** Phase 0 complete · Phase 1 in progress (this branch).

## Cross-references

- Architecture decision (learning side): mqobsidian PR #23 →
  `docs/command-learning-system.md`. This is the architecture contract for how
  workflow sequences become observations and proposals. **Merged 2026-06-25.**
- Plan shape contract: [`WORKFLOW_CONTRACT.md`](WORKFLOW_CONTRACT.md)
  (`mq-workflow-plan.v1`).
- Not to be confused with [`B2_WORKFLOW_CONTRACT.md`](B2_WORKFLOW_CONTRACT.md)
  (the separate B2 prompt-OS pipeline).

## Fixed ownership boundary

```text
mqlaunch   = operator surface
mq-agent   = orchestration
mq-mcp     = execution
mqobsidian = observations and learning
```

No planning logic in `mqlaunch`. No general workflow state in Bridget. No
execution in `mqobsidian`.

---

## Goal

A bounded, safe workflow engine where:

```text
mqlaunch → mq-agent workflow → mq-mcp tools
```

and completed sequences can be observed by `mqobsidian/memory/commands`.

The key system insight: it is not important that Bridget can make multiple tool
calls. What matters is that the system knows **which state it is in between tool
calls**. A prompt can suggest steps; a state machine can guarantee order,
conditions, stop, resume, evidence, safety, and reproducibility.

## Non-goals for v1

- No unbounded autonomous agent.
- No automatic `git commit`, `git push`, or release.
- No automatic learn-promotion.
- No two-way sync between `mq-mcp` and `mqobsidian`.
- No workflow engine inside `bridge.py`.
- No general composed `shell_exec`.
- No parallel execution in v1.

---

## Phase 0 — Lock the architecture  ✅

**Repo:** `mqobsidian` · **Behavior change:** no

- [x] Merge mqobsidian PR #23 (merged 2026-06-25).
- [x] `docs/command-learning-system.md` is the architecture contract.
- [x] No implementation mixed into the architecture PR.
- [x] Separate roadmap file created in `mq-agent` (this file).
- [x] Roadmap references the command-learning contract.
- [x] Fixed ownership boundary documented (above).

**Gate:** PR #23 merged · no unclear repo owner · no implementation in the wrong
repo · `commands`, `workflow`, `learn` have distinct meanings.

---

## Phase 1 — Workflow contract in `mq-agent`  ◀ this branch

**Branch:** `feat/workflow-contract-v1` · **Behavior change:** no · schema, types
and docs only.

Files:

```text
schemas/workflow-plan.v1.json
docs/WORKFLOW_CONTRACT.md
mq_agent/workflows/__init__.py
mq_agent/workflows/models.py
tests/test_workflow_contract.py
```

Minimal plan and step shapes, statuses, and validation rules are specified in
[`WORKFLOW_CONTRACT.md`](WORKFLOW_CONTRACT.md).

Tasks:

- [x] JSON schema.
- [x] Python data models.
- [x] Unknown fields are errors.
- [x] Unique `step.id`.
- [x] `depends_on` references existing steps.
- [x] Cyclic dependency detection.
- [x] `max_steps` capped at 10.
- [x] Default `max_steps=6`.
- [x] `max_replans=0` in v1.
- [x] Empty tool name forbidden.
- [x] `shell_exec` forbidden in the schema phase.
- [x] Documented that plan files are not the truth about live runtime.

Tests: valid plan accepted; unknown status rejected; duplicate ids rejected;
missing dependency rejected; dependency cycle rejected; more than ten steps
rejected; unknown top-level fields rejected; `shell_exec` rejected.

**Definition of Done:** `pytest tests/test_workflow_contract.py` passes and the
PR contains no actual execution.

---

## Phase 2 — Local workflow state

**Branch:** `feat/workflow-state-v1` · **Depends on:** Phase 1 merged.

Files: `mq_agent/workflows/state.py`, `storage.py`,
`tests/test_workflow_state.py`, `tests/test_workflow_storage.py`.

Storage: `${XDG_STATE_HOME:-$HOME/.local/state}/mq-agent/workflows/` with
`run_<id>.json` files and a `latest.json`. Never in the target repo, never in
Git.

Tasks: create run id; atomic save (temp file + rename); `created_at`/`updated_at`;
current step; attempt count; sanitized result summary; no secrets / raw env;
`load_run`, `save_run`, `list_runs`, `cancel_run`, `latest_run`.

Resume rules: `passed` never re-runs; `failed` re-runs only after explicit
resume; `running` from a dead process becomes `paused`; `cancelled` cannot be
resumed without a new run; a mutating step never auto re-runs.

**DoD:** a run can be created → saved → loaded → paused → resumed → cancelled
without any tool call.

---

## Phase 3 — Three fixed templates

**Branch:** `feat/workflow-templates-v1` · **Depends on:** Phase 2 merged.

Templates: `repo-preflight`, `review-and-test`, `release-ready`.

- **repo-preflight:** `run_mqlaunch_doctor` → `run_mqlaunch_selftest` →
  `run_mqlaunch_release_check` → summary. Stop on any failure; release-check only
  if both prior pass; no code writes; no push; no replan.
- **review-and-test:** git diff/status → review diff → run tests → summary.
  No diff = `completed` (not failed); review warnings don't block tests; test
  failure = `failed`; review result stored only as a summary.
- **release-ready:** repo status → repo-signal readiness → tests/selftest →
  release-check → summary. Dirty tree shown clearly; release-check skipped if
  test signal red; no release, tag, or push.

CLI: `mq-agent workflow list | show <t> | plan <t> --repo <path>`.

**DoD:** all templates validate against the schema; all tool names exist in the
MCP catalog; no free shell commands; clear stop conditions.

---

## Phase 4 — Read-only runner in `mq-agent`

**Branch:** `feat/workflow-runner-readonly` · **Depends on:** Phase 3 merged.

Runner loop: select next step → verify dependencies → verify condition → verify
policy → execute tool → normalize result → persist state.

v1 rules: `max_steps=6`, `max_replans=0`, `parallelism=1`,
`stop_on_failure=true`, `shell_exec=forbidden`, `mutation=forbidden`.

Normalize results to `{ "ok", "summary", "code", "data" }`; raw output never
becomes workflow truth; per-step timeout (default 120s); stop on unknown tool or
contract drift; persist before and after each call.

CLI: `mq-agent workflow run|status|resume|cancel`.

**DoD:** `mq-agent workflow run repo-preflight --repo /Users/mansys/macos-scripts`
produces a persistent run state with three clear steps.

---

## Phase 5 — Tool policy from `mq-mcp`

**Branch:** `feat/workflow-tool-policy` · **Depends on:** Phase 4 working with a
temporary static allowlist.

MCP tools: `list_tool_policies`, `get_tool_policy`. Policy result includes
`class`, `write`, `subprocess`, `network`, `side_effects`, `approval`,
`workflow_allowed`, `idempotent`, `retry_safe`.

Approval levels: `none` / `plan` / `step` / `forbidden` (see WORKFLOW_CONTRACT).

CI must find tools without policy and policy for nonexistent tools. Classify
existing `run_mqlaunch_*`; mark TUI-only tools `workflow_allowed=false`.

Do **not** change Bridget `approval_gate` in the same PR; no mutating workflows;
no free `shell_exec`.

**DoD:** mq-agent can ask "may this tool be in a workflow? which approval level?
can it re-run safely?" without a hardcoded list.

---

## Phase 6 — Policy-based runner

**Branch:** `feat/workflow-policy-gates` · **Depends on:** Phase 5 merged.

Fetch policy before plan validation; snapshot policy in run state; deny
`workflow_allowed=false` and unknown policy; deny mutation in read-only mode;
require plan approval for Class D read-only subprocess; no auto retry when
`retry_safe=false`; show side effects before approval; log approval decisions;
stop if policy changes during a paused run.

**DoD:** no tool executes without the runner first checking its current policy.

---

## Phase 7 — Thin `mqlaunch flow` surface

**Repo:** `macos-scripts` · **Branch:** `feat/mqlaunch-workflow-entrypoint` ·
**Depends on:** Phase 6 merged.

`mqlaunch flow [list|repo-preflight|review-and-test|release-ready|status|resume|cancel]`
routes to `_run_agent workflow "$@"`. mqlaunch may show menus, forward args,
show results, show approval prompts, show latest run id. It may not select tools,
interpret results, change state, implement conditions/retry, or hardcode safety
classes.

**DoD:** `mqlaunch flow repo-preflight /Users/mansys/macos-scripts` runs the
first full chain.

---

## Phase 8 — Bridget as workflow entrypoint

**Repo:** `mq-mcp` then `mq-agent`, separate PRs · **Depends on:** `mqlaunch flow`
stable.

`bridget --workflow "..."`. Bridget may extract goal, identify repo, propose a
known template, ask mq-agent to plan, present plan and final result. It may not
hold run state, implement retry, write workflow state, build free shell chains,
or bypass tool policy.

Keep `bridget --do` as legacy single-session mode; later route complex `--do`
tasks to the workflow engine. Recursion guard: `MQ_WORKFLOW_DEPTH=1`; deny new
workflow when depth > 0; deny `run_mqlaunch_*` that tries to start `mqlaunch
flow`; deny Bridget calling itself.

**DoD:** Bridget can start a known workflow but cannot execute an unbounded
autonomous flow.

---

## Phase 9 — Workflow observations in `mqobsidian`

**Branch:** `feat/workflow-observations-v1` · **Depends on:** at least one stable
workflow.

Extend observation type with `workflow_id`, `template`, `repo`, `task_type`,
`tool_sequence`, `outcome`, `failed_step`, `duration_ms`, `approval_count`.
Store only sanitized tool names and results — no full prompts, no raw stdout, no
secrets, no absolute private paths in public-safe material. Add sequence
frequency / success / avg duration / failure-step frequency / approval count.
Generate proposals, never automatic promotion.

New views: `workflow-top-reusable.md`, `workflow-failure-points.md`,
`workflow-by-repo.md`, `workflow-proposals.md`.

**DoD:** mqobsidian can show which sequences recur without being able to run them.

---

## Phase 10 — Limited adaptive planning (not MVP)

**Repo:** `mq-agent` · **Depends on:** fixed templates have real evidence.

Allow `max_replans = 1`. Permitted: choose between already-approved templates;
skip an irrelevant read-only step; add an approved diagnostic read-only step;
stop early when the goal is reached. Not permitted: arbitrary tool chains,
mutations, `shell_exec`, changing approval level, exceeding `max_steps`, starting
another workflow.

**DoD:** adaptivity improves information flow but never changes the safety
boundary.

---

## Phase 11 — Mutating workflows (later, separate decision)

Requires: stable read-only workflows; tested resume; policy drift guard;
rollback model; defined idempotency; approval audit; working observation loop;
at least three read-only templates with real usage data. Still forbidden without
a new decision: automatic push, merge, release, branch-protection bypass,
learn-promotion.

---

## PR order (strict)

| Order | Repo | PR |
|------:|------|----|
| 0 | mqobsidian | Merge #23 ✅ |
| 1 | mq-agent | Workflow contract ◀ |
| 2 | mq-agent | Local workflow state |
| 3 | mq-agent | Fixed templates |
| 4 | mq-agent | Read-only runner |
| 5 | mq-mcp | Tool-policy API |
| 6 | mq-agent | Policy-based gates |
| 7 | macos-scripts | `mqlaunch flow` entrypoint |
| 8 | mq-mcp | Bridget workflow delegation |
| 9 | mqobsidian | Workflow observations |
| 10 | mq-agent | Limited adaptive planning |
| 11 | several | Mutating workflows (separate decision) |

Do not mix repos in one PR.

---

## First real proof-of-concept

```text
mqlaunch flow repo-preflight /Users/mansys/macos-scripts

[1/3] mqlaunch doctor        PASS
[2/3] mqlaunch selftest      PASS
[3/3] mqlaunch release-check PASS
Workflow completed
```

On failure, dependent steps do not execute and the run is resumable after the
failure is fixed.

---

## v1 Definition of Done

`mqlaunch flow repo-preflight` works; mq-agent owns all workflow state; mq-mcp
owns all tool execution; every tool has a workflow policy; no unknown tool runs;
no `shell_exec`; no mutation; failure stops dependent steps; a paused run
resumes; passed steps don't repeat; state lives outside Git repos; recursive
workflow start is blocked; results can be shown as JSON; a sanitized workflow
observation can be created; mqobsidian proposes patterns but promotes nothing
automatically; Bridget can delegate to the runner; `bridge.py` is not the
workflow engine.
