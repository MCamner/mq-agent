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
- reports the calibrated thresholds as:
  - 20 observations, derived from 2 routes x 10 samples per route;
  - 2 candidate routes;
  - 14 days of coverage;
  - 10 samples per route;
- records that the calibration was reviewed against the repository-documented
  real applied `docs-review` history;
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

## Calibration result

The calibration review is complete and recorded in
[learned-routing-readiness-calibration.md](learned-routing-readiness-calibration.md).

The old 30-observation floor had no independent effect once the gate also
required two routes with ten samples each. It is now derived as 20. The
two-route, ten-per-route and 14-day requirements remain unchanged.

The last repository-documented real applied population reached only 14
observations, two routes, 3.502 days and five samples on the smaller route.
That evidence can justify removing redundancy; it cannot justify lowering the
per-route or temporal requirements.

## Next focus

Collect current-era real applied `docs-review` evidence until both allowlisted
routes reach ten samples across at least 14 days. A passing readiness report
then permits an explicit operator promotion review; it still does not authorize
automatic routing.

## Non-goals

This step does not:

- enable automatic routing;
- add a learned-routing activation command;
- expand the applied-route allowlist;
- lower the per-route or temporal readiness thresholds to fit the existing data;
- infer eligibility from execution outcomes;
- permit routing policy to decide privilege or safety;
- convert a passing readiness report into authorization.

Any future activation design remains a separate explicitly approved roadmap
slice after calibration and sufficient real evidence.
