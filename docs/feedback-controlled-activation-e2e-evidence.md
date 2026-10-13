# Controlled activation E2E evidence

Recorded from an operator-run on 2026-10-13 against `mq-agent` main at
`0bf340ccdfe7fea6897b98c9eee313222d581a52`, the squash merge of PR #390.

This receipt records public-safe identifiers and measured outcomes from the
operator-local append-only Feedback Engine store. The runtime JSONL records
remain local and authoritative for the individual event payloads; this document
does not reconstruct, rewrite or strengthen them.

## Scope

Task class: `repo-review`.

Controlled strategy transition under test:

```text
context-pack-v1
-> context-pack-v1+codegraph-guidance
-> context-pack-v1
```

The first arrow is the explicitly approved activation. The second is the exact
rollback proof.

## Approval and Canary v2

Candidate:

```text
cand-c0550c6f-59fe-42d5-a0d9-2327381f0a22
```

Activation-test approval:

```text
approval-29d00be6-9ac3-4513-af32-032371285fb4
```

Canary:

```text
canary-408e6cd4-f500-4a4d-9d9e-f418ba3d9bcd
```

The canary used three distinct real `repo-review` execution outcomes already
bound into the approved readiness evidence:

```text
5fcfbec7-b9ee-4618-87b0-5b5cdd7ff7dd
56666064-5ee6-4191-9f42-dc6d2a29cc17
a570e1bb-ff71-41a2-9f37-75cb69afb792
```

Observed Canary v2 result:

| Field | Result |
| --- | --- |
| Verdict | `PASS` |
| Executions requested | 3 |
| Executions completed | 3 |
| Successes | 3 |
| Failures | 0 |
| Inconclusive | 0 |
| Failure rate | 0.0 |
| Blocked reasons | none |
| Regressions | none |

Canary feedback runs:

```text
fb-cd23305d-ebdf-4e75-a22f-5b9347594e79
fb-d3377db7-5918-4665-bffa-1416ee7999ef
fb-1d658ec1-6df6-427f-bd91-1dfd37d3a5f2
```

Canary comparisons:

```text
cmp-7ef71565-4346-4832-8eda-5246fadceee2
cmp-823b94d8-b87f-4c3b-972b-757df51f0cd0
cmp-57ce0aee-9b43-4835-a054-281d5bb54d02
```

## Promotion and activation

Promotion approval:

```text
approval-promotion-970b43a3-430c-4435-bd3f-37ba8eec09a9
```

Its status was `VALID` with all recorded checks true:

- resolved
- not revoked
- not expired
- candidate match
- policy match
- canary match

Activation event:

```text
policy-e0ec2307-cd00-46e6-a713-e72ee6ee19c8
```

Observed transition:

```text
repo-review:
context-pack-v1
-> context-pack-v1+codegraph-guidance
```

Policy snapshot binding:

| Role | Snapshot |
| --- | --- |
| Before | `snapshot-eb6670b1-9e97-4901-8477-164b8149336f` |
| After | `snapshot-ec2f4655-d02d-4c75-be7d-0c85a6fe3d83` |
| Rollback target | `snapshot-eb6670b1-9e97-4901-8477-164b8149336f` |

The read-only policy view confirmed the effective strategy was
`context-pack-v1+codegraph-guidance` with the kill switch on.

## Fresh post-activation verification

A new real `repo-review` execution was recorded after activation:

```text
execution:  7d8ff205-d595-446a-b7de-e1e7b1d14fd5
feedback:   fb-63cde4fe-5732-4145-b99c-fe7757ca2883
comparison: cmp-1563cab0-c6ee-4048-a854-f80c0053dc70
```

At this point the experiment correctly reversed the comparison roles:

```text
active: context-pack-v1+codegraph-guidance
shadow: context-pack-v1
```

The deterministic comparison verdict was `CANDIDATE_WORSE`: after activation,
the shadow candidate is the old baseline, so this verdict means the baseline
was materially worse on the labelled quality evidence.

The policy-aware post-activation check returned:

```text
status: PASS
regressions: []
```

Measured evidence:

| Metric | Active | Shadow | Delta (shadow - active) | Material |
| --- | ---: | ---: | ---: | --- |
| Retrieval latency | 978.001 ms | 90.398 ms | -887.603 ms | no |
| Execution latency | 35352.0 ms | 35352.0 ms | 0.0 ms | no |
| Relevance precision | 1.0 | 1.0 | 0.0 | no |
| Relevance recall | 1.0 | 0.08 | -0.92 | yes |
| Context bytes | 1854 | 1253 | -601 | no |

The extra retrieval latency was about 2.51% of the exact correlated real task
runtime, below the existing 10% materiality threshold. No threshold was changed
for this proof.

## Exact rollback

Rollback event:

```text
policy-710db18f-87e1-43bd-b2ce-f3873bc0e81d
```

It was bound to the exact activation:

```text
rollback_of: policy-e0ec2307-cd00-46e6-a713-e72ee6ee19c8
rollback_target: snapshot-eb6670b1-9e97-4901-8477-164b8149336f
```

Observed rollback transition:

```text
context-pack-v1+codegraph-guidance
-> context-pack-v1
```

Final policy state:

| Field | Result |
| --- | --- |
| Baseline | `context-pack-v1` |
| Effective | `context-pack-v1` |
| Kill switch | `on` |
| Policy events | 2 |
| Policy snapshots | 3 |

## Interpretation

This closes the roadmap goal to prove the Post-v1.30 controlled activation gate
end to end on real `repo-review` evidence:

```text
real execution evidence
-> deterministic comparison
-> candidate
-> readiness
-> human approval
-> Canary v2 PASS
-> promotion approval
-> task-class-isolated activation
-> fresh post-activation verification PASS
-> exact snapshot-bound rollback
-> baseline restored
```

The proof is intentionally narrow. It validates the `repo-review` control
plane and its rollback semantics; it does not claim equivalent evidence for
other task classes.

No raw prompt, source body, diff, credential, private path or unrestricted tool
output is recorded in this receipt.
