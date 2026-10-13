# Execution completeness implementation plan

## Goal

Prevent partial documentation audits from becoming execution PASS evidence, while preserving applied-routing history.

## Owner repo

mqobsidian owns `schemas/mq.execution-outcome.v1.json`.

## Secondary repos

mq-agent owns executor measurements, audit output, telemetry emission and route-quality cohorts.

## Architecture boundary

- mqobsidian owns the canonical schema; mq-agent vendors the merged file exactly.
- Executor measurements determine completeness; model verification cannot override partial execution.
- Readiness counts real applied routing history. Quality requires a complete, successful linked execution.

## Non-goals

- No evidence deletion, correction, backfill, route allowlist change or automatic routing.
- No higher fan-out cap or claim that grounded quotations prove model suggestions.

## Approval gates

- File writes: authorized by the requested fix; use isolated worktrees.
- Commit and push: explicit operator approval before publishing.
- Merge: explicit operator approval after exact-head checks.
- Deletion/settings changes: excluded.

## Test gates

- Owner: `python -m unittest discover -s tests -p test_execution_outcome_contract.py -v`
- Consumer: `python -m pytest tests/test_execution_outcome.py tests/test_docs_audit_targets.py tests/test_analysis_cohort.py tests/test_route_divergence.py -q`
- Consumer release: `./release-check.sh` and `python scripts/check-vendored-contracts.py --help` followed by its supported owner-main comparison.

## Rollback

Revert code changes through PRs. Preserve schema compatibility and all existing evidence. Suspend quality collection if completeness cannot be established.

## Tasks

1. Add optional structured `completeness` to the canonical execution schema. Keep result vocabulary PASS/FAIL/SKIPPED; partial execution is FAIL with `completeness.status=partial`. Historical absence means unmeasured. Test complete/partial payloads, contradictory PASS, missing fields, malformed counts and historical compatibility.
2. Publish and merge the owner change after exact-head checks. Record its real merge commit; do not vendor an unmerged schema.
3. Vendor that exact merged schema. Aggregate completeness from executor step status and measured source/executed counts. Unknown fan-out completeness, skipped/failed/unexecuted steps and an empty plan cannot claim complete.
4. Propagate completeness through DocsAgent and docs-audit into the execution record. PASS additionally requires deterministic completeness and successful verification. Return nonzero for partial/failed audit, print structured result and observable execution id plus recording confirmation. Use scratch stores in tests.
5. Make route-quality analysis resolve routing `execution_run_id` against exact execution records and exclude incomplete, missing, ambiguous or unsuccessful executions with explicit exclusion counts. Keep readiness independent. Check explicit-source semantics and all quality readers, including route evidence-review.
6. After the consumer fix merges, add an execution-completeness era using its actual merge timestamp and commit. Test boundary inclusion, historical quality exclusion and unchanged readiness. Do not invent a future merge identity or timestamp.
7. Only after integration, resume real quality collection: complete successful audits, both routes, at least ten each across at least fourteen days. A capped full-repo audit remains partial; collection must use a genuine declared scope that completes.

## Current evidence

Two real applied observations were collected before this fix. Their route verification passed, but both audits read only 25 of 91 documentation items and 25 of 200 Python items. Their execution PASS labels do not establish complete audits. Leave both stores unchanged.
