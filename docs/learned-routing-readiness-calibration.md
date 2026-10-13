# Learned routing readiness calibration

Recorded 2026-10-13 from the repository-documented real applied
`docs-review` evidence and the current routing contracts.

## Decision

Calibrate the readiness gate to:

| Requirement | Before | Calibrated | Rationale |
| --- | ---: | ---: | --- |
| Minimum observations | 30 | 20 | Derived from 2 routes x 10 samples/route; the extra 10 had no independent evidence role |
| Candidate routes | 2 | 2 | A comparison needs at least two distinct applied strategies |
| Minimum samples per route | 10 | 10 | The independent divergence floor is also 10; real history reached only 5 on the smaller route |
| Minimum window | 14 days | 14 days | Real history reached only 3.502 days, which cannot justify shortening the temporal gate |

Passing this gate remains `AWAITING_OPERATOR_APPROVAL`. It does not grant
eligibility, edit the applied-route allowlist, or enable automatic routing.

## Real applied evidence used

These are repository-documented snapshots of the operator-local append-only
routing store. They are historical evidence, not a claim about the live store
on 2026-10-13.

| Repository evidence | Applied observations | Routes | Window | Minimum per route | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| PR #220 | 2 | 1 | early chain | 2 | `NOT_ELIGIBLE` |
| PR #223 | 4 | 2 | below temporal gate | 2 | `NOT_ELIGIBLE` |
| PR #243 | 9 | 2 | 1.884 days | 4 | `NOT_ELIGIBLE` |
| PR #258 | 14 | 2 | 3.502 days | 5 | `NOT_ELIGIBLE` |

PR #258 also opened the `evidence-integrity` quality era. At that boundary the
current-era route-divergence cohort was empty while readiness correctly retained
the 14 real applied observations across eras. That separation remains
intentional:

```text
readiness
  = has the mechanism applied both routes often enough and long enough
  = all valid applied history

route divergence
  = how the routes differ as the current implementations exist
  = current comparable era only
```

## Why 30 becomes 20

The previous gate required all of:

```text
observations >= 30
routes >= 2
samples_per_route >= 10
```

The last two requirements already imply at least 20 observations. The extra ten
could be placed entirely on one route, so it did not add balance. Temporal
coverage is already represented separately by the 14-day gate.

Keeping 30 would therefore add volume without a distinct safety or evidence
property. The calibrated gate derives the total floor from the two independent
balance requirements instead of maintaining a fourth arbitrary number.

## Why 10 per route stays

The real documented store reached five observations on the smaller route. That
is below both the old readiness floor and the independently implemented
`route divergence` comparison floor of ten per route.

Lowering the gate to five because five happens to exist would fit the sample
rather than calibrate a policy. Ten stays as a conservative minimum for opening
an operator review. It is still an eligibility threshold, not statistical proof.

## Why 14 days stays

The real documented history covered 3.502 days. That proves the mechanism can
accumulate multi-day evidence; it does not show that three or four days captures
weekday/load/model/runtime variation well enough for a learned-policy review.

The 14-day requirement is therefore retained as a conservative temporal
coverage target. This review does not claim that 14 days is statistically
optimal.

## Signals and authority

A future operator promotion review may inspect measured route divergence such as:

- verification pass and escalation rates;
- explicit escalation reasons;
- evidence grounding ratio and grounded items per measured observation;
- model-output availability;
- latency or other measured operational signals when available.

No scalar route-quality score is introduced. Structural differences such as
`deterministic-local` producing no model output remain descriptive, not
automatically good or bad.

The following remain authority boundaries rather than evidence signals:

- explicit `APPLIED_ROUTE_ALLOWLIST`;
- route-level safety veto;
- per-step `SafetyGate`;
- privilege and safety policy.

Telemetry cannot modify any of them.

## Next evidence gate

Collect current-era applied `docs-review` observations from both allowlisted
routes:

```text
local-shadow
deterministic-local
```

Do not open an automatic-routing design until:

1. each route has at least 10 applied observations;
2. the applied population spans at least 14 days;
3. current-era route divergence is inspectable rather than
   `INSUFFICIENT_EVIDENCE`;
4. an operator explicitly reviews the measured differences.

Even then, readiness may only open a promotion review. Automatic routing remains
disabled until a separate explicitly approved activation design exists.
