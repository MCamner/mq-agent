---
name: mq-feedback-control-plane
description: Use when operating or changing mq-agent's evidence-gated feedback control plane: readiness, human approval, post-approval canary, task-class activation, regression checks, rollback, kill switch, or policy consumption.
---

# MQ Feedback Control Plane

Use this skill for the v1.31 evidence-gated path from measured feedback evidence to one bounded task-class policy change.

## When to use

- Reviewing or changing Feedback Engine activation logic
- Moving a candidate from readiness to human approval
- Running or validating a post-approval canary
- Activating one task class with explicit operator approval
- Checking post-activation regressions
- Rolling back an activation
- Auditing the feedback kill switch or policy-consumer boundary

## When not to use

- Read-only feedback experiment/report work that does not touch activation policy
- General release preparation — use `release-readiness`
- Cross-repo contract ownership changes — use `mq-contract-owner-migration`
- Generic CI diagnosis — use `ci-diagnosis`

## Evals

### Should trigger

- "approve this feedback candidate and run the canary"
- "why is feedback activate refusing this candidate?"
- "add a regression check after activation"
- "verify rollback cannot toggle the old candidate back on"
- "check that --codegraph auto is unchanged by the feedback policy"
- "test the MQ_FEEDBACK_ACTIVATION kill switch"

### Should not trigger

- "show recent feedback experiments" → use the normal feedback read surface
- "bump mq-agent and publish" → use `release-readiness`
- "the canonical schema belongs in mqobsidian" → use `mq-contract-owner-migration`
- "CI is red" → use `ci-diagnosis`

## Invariants

The control plane is fail-closed.

- Readiness is evidence, not approval.
- Approval is explicit, content-bound, and may expire.
- Canary evidence must be recorded after the exact approval receipt.
- Activation is scoped to one task class.
- Activation and rollback are append-only policy events.
- Rollback must only reverse the currently active activation; it must never act as a toggle.
- Existing default consumer behavior must not change merely because a policy exists.
- Feedback policy consumption is explicit through `--codegraph policy`.
- `MQ_FEEDBACK_ACTIVATION=off` restores baseline behavior without deleting evidence.
- There is no autonomous or global activation path.

## Files To Inspect

- `mq_agent/feedback/control.py`
- `mq_agent/feedback/cli.py`
- `mq_agent/feedback/readiness.py`
- `mq_agent/feedback/store.py`
- `schemas/feedback_approval.schema.json`
- `schemas/feedback_policy_event.schema.json`
- `docs/FEEDBACK_ENGINE.md`
- `tests/test_feedback_control.py`

## Operator Workflow

Start read-only:

```bash
mq-agent feedback activation-readiness <candidate-id> --json
mq-agent feedback candidate <candidate-id> --json
```

Issue human approval only after reviewing the bound evidence:

```bash
mq-agent feedback approve <candidate-id> \
  --reason "reviewed exact candidate evidence" \
  --approve \
  --json
```

Run a new post-approval canary:

```bash
mq-agent feedback canary-run <candidate-id> \
  --approval-id <approval-id> \
  --task "review release boundaries" \
  --fixture <relevance-fixture.json> \
  --json
```

Activate only the approved candidate and exact canary:

```bash
mq-agent feedback activate <candidate-id> \
  --approval-id <approval-id> \
  --canary-comparison-id <comparison-id> \
  --reason "bounded canary passed" \
  --approve \
  --json
```

Measure after activation and interpret from the active-policy perspective:

```bash
mq-agent feedback post-activation-check <task-class> \
  --comparison-id <comparison-id> \
  --json
```

Rollback on a material regression:

```bash
mq-agent feedback rollback <task-class> \
  --reason "material regression observed" \
  --approve \
  --json
```

## Change Rules

When modifying this control plane:

1. Preserve append-only evidence and policy history.
2. Add a negative test for every new refusal condition.
3. Prove stale approval, pre-approval canary, task-class mismatch, and repeated rollback fail closed.
4. Keep activation behind explicit operator approval.
5. Keep the baseline/default consumer path unchanged unless the change explicitly targets that contract.
6. Do not add an MCP or client-specific mutation path that bypasses mq-agent.

## Verification

```bash
python -m pytest tests/test_feedback_control.py -q
python -m pytest tests/test_feedback_activation_readiness.py -q
python scripts/check-feedback-release.py
./release-check.sh
```

For a production-policy change, also verify the exact PR head is green before merge.

## Report Format

Return:

- candidate/readiness status
- approval identity and whether it is still valid
- canary identity and snapshot
- effective task-class strategy
- post-activation regression status
- rollback target
- kill-switch state
- checks run and any unverified assumptions
