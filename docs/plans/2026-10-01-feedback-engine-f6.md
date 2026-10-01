# Feedback Engine F6 release hardening plan

## Goal

Prove the v1.30 Feedback Engine as a releaseable, installable, public-safe
feature without widening its authority.

F6 hardens F0-F5. It does not add activation, autonomous routing, direct
durable-memory writes, or a client-specific policy engine.

## Gates

- end-to-end deterministic fixture from experiment to report/candidate;
- mutation coverage for provenance, snapshot, duplicate-id, stale, malformed
  and unavailable-evidence cases;
- installed-wheel feedback schema and CLI checks;
- canonical release-check coverage for feedback contracts and packaging;
- real zero-effect repo-review shadow runs against mq-agent and mq-mcp in CI;
- README/public docs aligned with the stable command and ownership boundary;
- historical v1 readability;
- pre-tag checklist explicitly requires main CI, local release-check, stack
  contract-check and branch-protection check.

## Real-run evidence rule

The real CI runs are operational measurements only. Without an explicit
relevance fixture they must remain `INSUFFICIENT_EVIDENCE`; latency or smaller
context alone is not a quality verdict.

## Rollback

Revert the F6 PR. Runtime feedback evidence stays append-only and independent of
Git, so hardening changes can be rolled back without mutating historical
operator evidence.
