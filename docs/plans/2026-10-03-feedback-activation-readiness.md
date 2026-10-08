# Feedback activation readiness v1

> Historical design note: the original two-comparison/two-snapshot evidence
> floor below was deliberately provisional. It was superseded after v1.33 by
> outcome-derived per-task-class promotion criteria that correlate feedback
> experiments to exact `mq.execution-outcome.v1` runs. The blocker rules and
> human-approval/canary boundary remain in force.


## Goal

Add the first read-only gate for future Evidence-Gated Activation & Rollback.

This phase does not add approval storage, canary execution, activation,
production-policy writes, or rollback execution.

## Contract

The machine contract is `mq.feedback-activation-readiness.v1`.

The gate is candidate-scoped and task-class-isolated. It reports one of:

- `READY_FOR_HUMAN_APPROVAL`
- `INSUFFICIENT_EVIDENCE`
- `BLOCKED`

A ready result is deliberately not called APPROVED or ACTIVATABLE.

## Readiness requirements

Blockers:

- feedback candidate/comparison histories parse without invalid records;
- candidate kind is `context-strategy`;
- effective state is `proposed`;
- every candidate comparison id resolves exactly once;
- every comparison has the candidate task class;
- active/shadow strategy pair exactly matches current/proposed;
- every comparison is valid and `CANDIDATE_BETTER`;
- no linked comparison contains a material worse metric;
- rollback target exactly equals the current strategy.

Evidence floor:

- at least two linked comparisons;
- at least two distinct repository+Git-commit snapshots.

The repeated-snapshot rule prevents re-running one fixture on one checkout from
looking like independent evidence.

## Safety boundary

Every result carries:

```text
human_approval_required = true
canary_required = true
activation_available = false
cross_task_activation = false
```

The gate reads feedback history only. It appends no records and changes no
production behavior.

## Next phase

A later phase may define a human approval receipt and canary plan that consume
this contract. Neither should duplicate this gate's evidence rules.
