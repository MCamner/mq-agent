---
name: mq-evidence-integrity
description: Use before producing, correlating, labelling or counting MQ evidence (execution outcomes, feedback experiments, relevance fixtures, hybrid retrieval labels, readiness populations). Blocks synthetic, backdated, reconstructed or mislabelled evidence and checks that the producer did real work on the right target.
---

# MQ Evidence Integrity

The MQ control planes trust their evidence stores: readiness, canary and
activation decide from what is recorded there. Wrong evidence does not fail
loudly. It turns into a confident wrong decision. Every rule below comes from an
incident that happened, or nearly happened.

## When to use

- Collecting execution outcomes or feedback experiments for readiness
- Linking a feedback run to an execution with `--execution-run-id`
- Writing relevance fixtures or labelling retrieval candidates
- Instrumenting a command so that it records `mq.execution-outcome.v1`
- Judging whether a store holds enough real evidence to proceed

## When not to use

- Changing a shared schema across repos → use `mq-contract-owner-migration`
- Operating approval, canary or activation itself → use `mq-feedback-control-plane`
- Wording a PR or report → use `mq-verified-reporting`

## Evals

### Should trigger

- "the feedback store is empty, seed it so readiness passes"
- "link these old outcomes to the new repo-review experiments"
- "which run id belongs to the review I just ran?"
- "label these retrieval candidates and persist the ablation"
- "count audit outcomes as repo-review evidence"

### Should not trigger

- "add a field to the canonical execution outcome schema" → use `mq-contract-owner-migration`
- "write the PR description" → use `mq-verified-reporting`

## Hard rules

1. **Never create evidence that did not happen.** That includes synthetic seeding
   of a real store (test fixtures write to tmp stores only), editing
   `recorded_at`, and backfilling missing fields. An empty store is reported as
   EMPTY: a blocked step, not a gap to fill.
2. **Correlate only through an id observed at run time.** Use the run id the
   command reports while it runs, and nothing else. Do not reconstruct a link
   afterwards by diffing the store or matching timestamps. Concurrent writers
   make that ambiguous, and old outcomes carry dates that would fake temporal
   coverage.
3. **A run id is not proof that a record exists.** Telemetry is best-effort
   (`emit_execution_outcome` swallows failures). Use an id only when the producer
   also reports `execution_outcome_recorded: true`.
4. **Never map one task-class vocabulary onto another.** Feedback task classes
   and execution-outcome task classes are separate. `repo-review` is not `audit`.
   When a class is missing, the real producer has to gain it through the
   contract owner. Borrowing the nearest class is not allowed.
5. **The agent never authors labels.** Relevance labels and fixtures come from
   the operator. A label set drafted by AI counts only after the operator
   explicitly confirms it, and its provenance says "AI-drafted,
   operator-confirmed".
6. **Production stores are not test beds.** `_require_recordable_runtime`
   refuses production writes from a dirty or unintegrated checkout. To exercise
   a branch for real, redirect `MQ_AGENT_EXECUTION_OUTCOMES` and
   `MQ_AGENT_ROUTE_OUTCOMES` to a scratch directory.

## Check that the producer did real work

A PASS outcome must mean that the work happened, to the intended target. Before
treating a producer as an evidence source, run it once for real and read the
payload, not just the exit code:

- **Target:** a delegated tool resolves relative paths in *its own* working
  directory. Incident: `review repo .` reviewed the mq-mcp checkout because the
  bridge omits `repo_path` for `.`. Resolve paths to absolute before delegating,
  and confirm that the reported root is the intended repo.
- **Work done:** look for per-item failures hidden inside a success. Incident:
  without `OPENAI_API_KEY`, every file answered "requires OPENAI_API_KEY", the
  review reported "5 file(s) reviewed", and the outcome recorded PASS. That
  would have inflated readiness success rates.
- **Classification:** check the recorded `task_class`. A class missing from
  `KNOWN_TASK_CLASSES` is silently written as `unclassified`.

## Check claims against the data, not the premise

Before writing "the corpus has no X" or "the channel cannot find Y" into a doc,
query the data. Incident: a retrieval result was blamed on missing corpus
material. In fact 98 matching items existed, and the keyword channel was scoring
Swedish function words (`och`, `en`, `den`) because its stop-word list was
English only. Inspect `matched_terms` or the equivalent trace before choosing an
explanation.

## Stop conditions

Stop and report instead of proceeding when:

- the store is empty, or below the readiness floor
- the producer of the needed task class does not exist or is not instrumented
- the run id is not observable at run time
- a label set has no operator confirmation

Name the missing precondition and the smallest real way to obtain it.
