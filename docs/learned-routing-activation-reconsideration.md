# Learned routing activation reconsideration

Recorded 2026-10-13 after the Post-v1.30 controlled activation gate was proven
end to end on real `repo-review` evidence.

## Decision

Do **not** enable evidence-based or automatic learned routing yet.

The completed activation/rollback proof removes the previous control-plane
prerequisite for reconsidering learned routing. It does not by itself provide
routing-quality evidence or validate the routing-readiness thresholds.

## Repository evidence

The current routing implementation keeps authorization and evidence separate.

`route_readiness()`:

- considers only observations with `application == "applied"`;
- reports the existing thresholds as:
  - 30 observations;
  - 2 candidate routes;
  - 14 days of coverage;
  - 10 samples per route;
- explicitly says those numbers were carried over from a per-execution
  population and are **unreviewed** for a population of routing decisions;
- returns `grants_eligibility: false`;
- returns `automatic_routing_enabled: false`;
- returns `operator_approval_required: true`.

There is no `route learn` CLI command on `main`.

Applied routing is currently authorized only through the explicit
`APPLIED_ROUTE_ALLOWLIST` plus route-level safety checks. Accumulating
telemetry cannot add an allowlist entry or grant execution rights.

The currently allowlisted comparison pair is limited to `docs-review`:

```text
local-shadow
deterministic-local
```

Privilege and safety routing remain outside learned-routing authority.

## Interpretation

The roadmap condition at the end of the Post-v1.30 activation gate is now
satisfied: evidence-based routing activation has been reconsidered.

The result of that reconsideration is **BLOCKED pending calibration**, not an
activation design.

The control-plane E2E proof answers:

> Can an evidence-bound policy change be approved, canaried, activated,
> verified and rolled back safely?

It does not answer:

> Are the current route-readiness thresholds calibrated well enough to promote
> a learned routing policy?

Those are separate evidence questions.

## Next focus

Calibrate the learned-routing readiness gate using real applied
`docs-review` observations from both allowlisted routes.

The existing numeric thresholds may be used as observation targets while data
is collected, but they must not be treated as validated promotion policy until
the calibration review is complete.

The calibration review should establish:

1. whether routing-decision observations are independent enough for the current
   sample counts to be meaningful;
2. whether 14 days captures useful temporal variation for local route quality;
3. whether the 10-per-route floor prevents materially imbalanced comparisons;
4. which measured quality, latency, grounding and escalation signals may support
   a recommendation;
5. which signals are advisory only and must never authorize a route.

## Non-goals

This step does not:

- enable automatic routing;
- add a learned-routing activation command;
- expand the applied-route allowlist;
- change the existing readiness thresholds;
- infer eligibility from execution outcomes;
- permit routing policy to decide privilege or safety;
- convert a passing readiness report into authorization.

Any future activation design remains a separate explicitly approved roadmap
slice after calibration and sufficient real evidence.
