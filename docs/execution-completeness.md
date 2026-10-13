# Documentation audit completeness

Route verification checks the review produced from gathered material. Execution
completeness checks whether all declared audit work actually ran. Passing the
former does not establish the latter.

## Runtime behavior

`docs-audit` carries structured executor `completeness` through the audit payload
to `mq.execution-outcome.v1`. Step numbers in this measurement are one-based
plan positions. A nonempty plan is complete only when every step succeeded and
every fan-out completed with matching measured source and executed counts.
Failed, skipped, unexecuted, partial or unmeasured steps prevent completeness.
An empty plan is partial.

A partial audit records execution `FAIL` with `completeness.status: partial`
and exits nonzero. A complete audit can still fail verification; completeness
establishes coverage, not correctness. Route verification cannot override either
failure. The fan-out cap remains in place: a full-repo audit that reaches it is
still partial.

The canonical schema is owned by mqobsidian. Its optional completeness addition
merged in [mqobsidian PR #140](https://github.com/MCamner/mqobsidian/pull/140),
commit `281b82275fb44076221cae7cd9a67cb8227469e7`. mq-agent vendors that exact
merged schema. Historical records without the field remain valid; their
coverage is unmeasured, never implicitly complete.

## Evidence populations

Applied-routing readiness retains all real applied observations across eras.
It does not certify complete audits and grants no execution rights.

Complete `docs-review` quality requires the observation's recorded
`execution_run_id` to resolve to one exact execution record with successful
result and measured complete coverage. Missing, ambiguous, mismatched, partial
or unsuccessful executions are excluded explicitly. No link is reconstructed
from timestamps. With an explicit source, records must be provided together in
that source; the report does not borrow ambient operator data to fill gaps.

Two real applied observations collected on 2026-10-13 are preserved unchanged.
Both routes verified their review, while both full audits were partial: fan-out
read 25 of 91 documentation items and 25 of 200 Python items. Their historical
execution `PASS` labels do not prove complete audit quality.

## Integration and collection

Quality collection is paused. After this consumer fix merges, open the
`execution-completeness` quality era with that fix's actual merge commit and
timestamp in `mq_agent/tools/analysis_cohort.py`. The owner schema merge does
not define the producer's boundary. Do not predeclare a future merge identity
or move production observation timestamps.

Then use real audits of a declared scope that can complete: at least ten complete
successful executions for each of `deterministic-local` and `local-shadow`,
spanning at least fourteen days in the new era. Both commands still use OpenAI
for audit planning and verification; `deterministic-local` only removes model
inference from the routed review itself.

Read the structured payload and recording confirmation for every run. A zero
shell exit or a stored run id alone is insufficient. Review measured route
divergence only after the sample and time requirements are met, followed by
explicit operator promotion review. Automatic routing remains disabled.
