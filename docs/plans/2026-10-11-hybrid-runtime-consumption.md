# Hybrid Runtime Consumption Implementation Plan

## Goal

Define a bounded, explicitly approved retrieval consumer from verified positive
admission evidence, preserving active-only defaults.

## Owner repo

mq-agent.

## Secondary repos

mqobsidian for canonical contract ownership verification before schema work;
mq-mcp remains the active semantic search provider.

## Architecture boundary

- mq-agent owns retrieval orchestration, task-class gates and operator CLI.
- mqobsidian owns durable memory and canonical contracts where established.
- mq-mcp owns execution tools, safety and the active semantic search boundary.
- mq-hal owns operator summaries; repo-signal owns repository scoring.
- This plan proposes behavior. No runtime consumer or approval receipt exists
  as a result of writing it.

## Verified facts — 2026-10-11

Challenge `sha256:f700fae03a78681a55ff78e96b2eda1ec569d3416f83398ff173aedd1550c4f8`
is VERIFIED and discriminating. Admission
`sha256:9526d1b1c434e3071e825bc990aa400957db0f1994d1279ace103e5d68c7000d`
is VERIFIED, with `PASS` and `OPTIONAL_CHANNELS_ELIGIBLE`.

| Task class | Eligible channel | Precision / recall gain | Additional estimated tokens | Measured channel latency (ms) |
| --- | --- | --- | --- | --- |
| ci | codegraph | 0.20 / 0.667 | 6055 | 278.055 |
| docs | notebook-keyword | 0.10 / 0.333 | 1693 | 478.630 |
| docs | notebook-vector | 0.30 / 1.00 | 1298 | 263.206 |
| repo-review | notebook-keyword | 0.30 / 1.00 | 1565 | 489.752 |

These are stored singleton measurements, one case per task class. Latency is
total measured channel latency, not incremental end-to-end overhead. Token
counts are JSON character estimates, not provider tokenizer counts. No measured
quality regressions occurred; this is not evidence of general task-class safety.

The following zero-effect policy plans were persisted and individually VERIFIED:

- ci: `sha256:1eaaf42b9061ecacf8456a6978915155bff046c172b8da5ca39d5f0b49428aef`
- docs: `sha256:d6a245ad853cae811885fc7bdd2ca4c35ff7afcf3fad97ce37eca60c7476bb2b`
- repo-review: `sha256:3b85ae5cc61c731d02df31819e198b403e215b67a5ff0f0d25dd417ee8ca8ba8`

All return `REVIEW_REQUIRED`; effective optional channels remain false.
`audit_hybrid_policy_plans` explicitly requires ACTIVE_ONLY and therefore
returns REFUSED for this set. This is the existing closure gate's scope, not
corrupt evidence. Keep its existing behavior and add a separate proposal review.

## Recommended design

Start with `repo-review` plus notebook-keyword in an explicit memory retrieval
CLI invocation. It exercises one optional channel using the existing catalog
adapter. Defer automatic integration into agent commands until task-class
mapping and outcome correlation are explicit and tested. Eligible docs channels
do not by themselves prove that their combined runtime selection is safe.

Separate three identities: verified proposal, human approval receipt, effective
runtime selection. A receipt must bind the exact proposal, admission, challenge,
task class, selected channel, input fingerprints, runtime revision and budget.
Any mismatch or expired receipt refuses optional consumption.

Budget values must be supplied explicitly by the operator: maximum additional
estimated payload tokens, optional-channel timeout and receipt validity period.
Do not infer limits from one observed run. Missing, invalid or exceeded limits
keep the active-only result. Enforce the timeout before consuming the optional
result; record the fallback reason. Define the payload estimate before fusion
and retain that definition in the approval contract. Avoid treating the existing
historical latency field as a live timeout or cost delta.

Runtime opt-in must reference a verified receipt, not merely a policy-plan ID.
Re-verify its evidence and current input fingerprints before optional retrieval.
Active semantic search must succeed. Optional failure, timeout, budget overflow,
disabled consumption or revoked approval returns the active-only result.
Record effective selection and evidence identities without raw queries, local
paths or retrieved content. Rollback revokes one exact receipt; a kill switch
forces active-only. Neither operation deletes evidence.

## Alternatives and consequences

- Keep active-only: safest current behavior; leaves measured optional gains unused.
- Consume all eligible channels automatically: rejected; eligibility is not
  approval, joint behavior and budgets are not established.
- Explicit receipt-bound single-channel consumer: recommended; adds bounded
  operator work and new contracts, but keeps failures and rollback local.
- Reuse Feedback Engine receipts directly: deferred; its task-class vocabulary
  and execution evidence have different meanings. No implicit mapping.

## Non-goals

- Change RRF, top-k, relevance labels or production routing.
- Enable all classes, introduce an apply command, or activate a channel now.
- Weaken the existing active-only closure audit.

## Approval gates

- Before these documentation writes: no; requested by the operator.
- Before implementation: explicit acceptance of this plan and budget semantics.
- Before runtime consumption: explicit content-bound operator approval.
- Before commit or push/merge: separate authorization; not part of this task.
- Before deletion/settings changes: explicit authorization.

## Test gates

Existing regression command:

```bash
uv run pytest tests/test_hybrid_retrieval_v2.py tests/test_hybrid_retrieval_evidence.py -q
uv run ruff check .
git diff --check
```

## Rollback

Until implementation, revert only this plan and its ROADMAP reference. Once a
consumer exists, disable consumption or revoke its exact receipt to restore
active-only immediately; retain append-only evidence. Code rollback uses the
specific implementation commit through the normal PR flow.

## Implementation tasks — proposed, not implemented

### Task 1: Positive proposal review

Implemented locally on 2026-10-11 as `policy-proposal-review`. The live exact
ci/docs/repo-review set returned VERIFIED, errors=[], REVIEW_REQUIRED. The old
ACTIVE_ONLY closure audit retains its refusal behavior. No activation occurred.

Modify `mq_agent/memory/hybrid_evidence.py`, `mq_agent/main.py` and
`tests/test_hybrid_retrieval_evidence.py`. Add a separate read-only proposal
review that verifies the complete evidence chain and exact class/channel scope.
Test missing/tampered evidence, mismatched challenge/ablation, duplicate classes,
ineligible channels and preservation of ACTIVE_ONLY audit refusal behavior.
Run the existing regression command above. Commit suggestion:
`feat(hybrid): review positive channel proposals without activation`.

### Task 2: Approval and budget contract

Implemented locally on 2026-10-11 with mq-agent-owned approval and revocation
schemas, wheel packaging, immutable receipt storage and CLI commands `approval`,
`approval-status`, `approval-revoke`. No live approval was issued. The initial
scope is repo-review/notebook-keyword, and all records retain
`runtime_consumption_available=false` until a separate consumer is implemented.

Receipts bind the verified proposal-review fingerprint, policy plan, admission,
challenge, ablation, suite, catalog fingerprint, observed runtime commit, selected
scope, explicit budgets, approval time and expiry. Verification rebuilds that
binding against current evidence and inputs. Revocations retain the receipt and
are immutable records addressed by the exact target approval ID. A duplicate
revocation is refused, and malformed revocation state fails closed.

Budget semantics for Task 3: `max_additional_tokens` caps the additional optional
candidate-ref payload before fusion, estimated as the ceiling of the character
length of its JSON array divided by four. Serialize normalized optional refs with
`ensure_ascii=False`, `sort_keys=True`, and `separators=(",", ":")`. This is an
estimate, not billed/model-token cost. `optional_timeout_ms` caps wall time from
optional-channel invocation to completed optional retrieval. The consumer must
fall back when either limit is exceeded; current approval verification does not
claim these execution limits have been exercised.

Verification: 91 focused runtime, retrieval, evidence and command-reference tests
passed; Ruff and generated-reference checks passed. Offline wheel build passed;
both new schemas are valid, byte-equivalent as parsed to the source contracts,
and resolved from the extracted wheel. The local vendoring check reports an
existing execution-outcome drift (`fallback` is in mq-agent HEAD but absent from
the local mqobsidian canonical schema). This task did not modify that contract.

First verify ownership using `mq-contract-owner-migration`. Proposed consumer
files: `mq_agent/memory/hybrid_runtime.py`, `mq_agent/main.py` and
`tests/test_hybrid_runtime.py`; proposed contract:
`schemas/hybrid_retrieval_approval.schema.json`. Ownership verified on 2026-10-11:
mq-agent owns and packages the Hybrid Retrieval contracts; they are absent from
`schemas/vendored-contracts.json` and mqobsidian's canonical schema inventory.
The initial approval scope is repo-review/notebook-keyword. The CLI derives the
runtime commit through the existing runtime guard; it accepts no caller-supplied
revision. The Python verifier requires an independently observed revision.
Implement immutable approvals and revocations with all bindings and explicit
budgets. Test invalid budgets, expiry, stale inputs/revision and exact revocation.
Run `uv run pytest tests/test_hybrid_runtime.py -q` and owner/consumer contract
checks established by the migration plan. Commit suggestion:
`feat(hybrid): bind operator approvals to evidence and budgets`.

### Task 3: Explicit single-channel consumer

Implemented locally on 2026-10-11 as `memory retrieve`. Receipt-bound
repo-review/keyword opt-in uses unchanged RRF and measured top-k=10. Without
opt-in it uses active-only retrieval. The keyword worker is terminated and reaped
on timeout; budget overflow, stale/revoked approval or disabled consumption
preserves active-only references and the original active response. Approval,
catalog and kill switch are rechecked after the worker finishes. Returned traces
are sanitized and retrieval writes no state. No live approval or consumption was
performed; bounded operator validation remains Task 4.

Verification: 110 focused tests passed, including CLI opt-in/default/fallback,
a real subprocess deadline, exact token-budget boundary, in-flight revocation,
catalog/kill-switch changes and refusal of evidence measured at another top-k.
Ruff, generated command-reference and diff checks passed. The offline wheel
built and its subprocess worker returned the expected synthetic Notebook ref
from outside the source checkout. Active mq-mcp search and runtime identity were
stubbed in consumer integration tests; live operator validation is not claimed.

Modify `mq_agent/memory/hybrid_runtime.py`, `mq_agent/main.py` and
`tests/test_hybrid_runtime.py`; read-only references:
`mq_agent/memory/hybrid_retrieval.py` and `mq_agent/notebook_corpus_search.py`.
Implement repo-review/keyword opt-in, live limits, fallback and a kill switch.
Test unchanged default output, unknown class refusal, optional failure, timeout,
overflow, revoked approval and unavailable active search. Run both test commands
above and Ruff. Commit suggestion:
`feat(hybrid): consume one approved channel with active-only fallback`.

### Task 4: Bounded operator validation

Modify `ROADMAP.md`, `docs/ARCHITECTURE.md` and
`tests/test_hybrid_runtime.py`; regenerate
`docs/generated/Command-Reference.md` through the existing documentation flow.
Validate a bounded opt-in run using operator-reviewed fixtures, then prove
revocation and kill-switch fallback. Record actual overhead and budget outcomes.
Keep activation blocked until these checks pass. Commit suggestion:
`docs(hybrid): document bounded consumption and rollback evidence`.
