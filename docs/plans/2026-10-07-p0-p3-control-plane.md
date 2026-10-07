# MQ P0-P3 Control Plane Implementation Plan

## Goal
Close the remaining loop from evidence to controlled activation while adding runtime fallback evidence, perception orchestration, recoverable local state, session-to-memory handoff, and measured hybrid retrieval shadowing.

## Owner repo
mq-agent

## Secondary repos
mq-mcp and mq-image-analyze are consumed through existing stable interfaces; no ownership is moved.

## Architecture boundary
- mqobsidian owns durable truth, memory promotion boundaries, and published context contracts.
- mq-agent owns planning, feedback evidence, approval/canary/activation control, task-class policy selection, state snapshots, session handoff, and orchestration.
- mq-mcp owns semantic retrieval runtime, review logic, tool safety, and runtime reasoning.
- mq-image-analyze owns visual extraction and perception.v1 production.
- mq-hal owns operator summaries; this slice exposes stable JSON for later consumption.

## Non-goals
- no automatic approval or activation;
- no cross-task-class activation;
- no deletion of historical feedback evidence on rollback;
- no raw prompt, source body, tool stdout, credential, or private-path capture;
- no automatic durable-memory promotion;
- no new vector/graph backend;
- no duplicated review or perception engine inside mq-agent.

## Approval gates
- Before file writes: approved by user request to build P0-P3.
- Before commit/push: approved by user request to build in the connected repos.
- Before merge: only after required CI is green.
- Before policy activation at runtime: explicit CLI --approve and a valid non-expired approval receipt plus canary evidence.
- Before restore: explicit CLI --approve.

## Test gates
- targeted pytest for each new module;
- existing feedback, execution-outcome, review, notebook semantic, memory tests;
- full repository Tests, Install smoke, Markdownlint, MQ Stack Gate;
- release-check through normal CI.

## Rollback
- code rollback: revert the integration PR;
- runtime policy rollback: append a ROLLBACK event to the policy log; never rewrite history;
- kill switch: MQ_FEEDBACK_ACTIVATION=off makes context selection ignore activated feedback policies;
- state restore only writes from a verified snapshot manifest and requires --approve.

### Task 1: P0 evidence-gated activation and rollback
**Purpose:** turn READY_FOR_HUMAN_APPROVAL into a controlled, task-class-isolated approval/canary/activation lifecycle.

**Files:**
- Create: `mq_agent/feedback/control.py`
- Create: `schemas/feedback_approval.schema.json`
- Create: `schemas/feedback_policy_event.schema.json`
- Modify: `mq_agent/feedback/contracts.py`
- Modify: `mq_agent/feedback/store.py`
- Modify: `mq_agent/feedback/cli.py`
- Modify: `mq_agent/feedback/engine.py`
- Modify: `mq_agent/main.py`
- Create: `tests/test_feedback_control.py`

**Expected result:** approval is content-bound and expiring; canary evidence is bound to exact candidate/approval; activation appends a policy event; rollback appends another; context pack obeys the active task-class policy unless explicitly overridden.

### Task 2: P1 fallback telemetry and perception review
**Purpose:** measure real fallback reasons and expose perception as a first-class review orchestration path.

**Files:**
- Modify: `schemas/execution_outcome.schema.json`
- Modify: `mq_agent/tools/execution_outcome.py`
- Modify: `mq_agent/main.py`
- Modify: `mq_agent/tools/mcp_bridge.py`
- Modify: `tests/test_execution_outcome.py`
- Modify: `tests/test_review_cli.py`

**Expected result:** execution records may carry a structured measured fallback; `mq-agent review perception` delegates visual extraction to image_perception and review/risk reasoning to existing mq-mcp review surfaces without implementing either engine.

### Task 3: P2 state snapshot/restore and session handoff
**Purpose:** make local MQ evidence portable and make long agent sessions produce typed, reviewable memory candidates.

**Files:**
- Create: `mq_agent/tools/state_snapshot.py`
- Create: `mq_agent/memory/session_handoff.py`
- Create: `tests/test_state_snapshot.py`
- Create: `tests/test_session_handoff.py`
- Modify: `mq_agent/main.py`

**Expected result:** inventory/snapshot/verify/restore works over declared local state only; session handoff emits memory-observation.v1 candidates with typed facts and no raw transcript.

### Task 4: P3 hybrid retrieval shadow mode
**Purpose:** compare active semantic-memory retrieval with a deterministic hybrid candidate without changing the active answer path.

**Files:**
- Create: `mq_agent/memory/hybrid_shadow.py`
- Create: `tests/test_hybrid_shadow.py`
- Modify: `mq_agent/main.py`

**Expected result:** `mq-agent memory hybrid-shadow` returns active and shadow result identities, deterministic merge trace, provenance coverage, latency, and divergence; active retrieval remains authoritative.

### Task 5: docs, command reference, release evidence
**Purpose:** keep public command and safety surfaces aligned.

**Files:**
- Modify generated command reference using the repo generator.
- Update relevant feedback/memory docs and roadmap checkboxes.
- Run full CI.

## Skills applied
- repo-aware
- mq-writing-plans
- mq-subagent-driven-development (task/spec/quality loop)
- mq-worktree-safe principles (isolated branch, clean main baseline)
- mq-mcp-review-orchestration
- feedback-review
- semantic-memory-maintainer
- mcp-tool-safety-maintainer
- runtime-observability-maintainer
- integration-stack-maintainer
- json-contract-maintainer
- release-readiness
