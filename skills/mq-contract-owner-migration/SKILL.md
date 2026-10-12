---
name: mq-contract-owner-migration
description: Use when an MQ contract must change across repositories. Enforces canonical-owner-first schema changes, tests, merge evidence, exact vendoring into consumers, and drift-gate verification.
---

# MQ Contract Owner Migration

Use this skill whenever a shared MQ contract changes and one repository owns the canonical schema while other repositories vendor or consume it.

## When to use

- Adding a field to a shared MQ schema
- Moving a contract from one owner repository to another
- Fixing canonical-versus-vendored schema drift
- Updating a producer and one or more consumers together
- Repairing a stack contract gate that reports a consumer ahead of canonical truth

## When not to use

- A schema owned and consumed only inside one repository
- General release preparation — use `release-readiness`
- Feedback activation policy — use `mq-feedback-control-plane`
- Repository-wide code quality audit — use `repo-audit`

## Evals

### Should trigger

- "mq-agent's vendored execution outcome schema is ahead of mqobsidian"
- "add a field to a canonical MQ contract and sync all consumers"
- "which repo should own this schema?"
- "the contract gate says vendored schema drift"
- "migrate this contract owner without breaking old readers"

### Should not trigger

- "add a private internal dataclass" → normal repo implementation
- "prepare the next release" → use `release-readiness`
- "activate this feedback candidate" → use `mq-feedback-control-plane`
- "audit state restore safety" → use `mq-state-recovery-audit`

## Canonical-First Rule

Never make the consumer authoritative by accident.

The safe order is:

```text
canonical owner
    ↓
canonical schema + owner tests
    ↓
owner PR green
    ↓
owner merge
    ↓
exact consumer vendoring
    ↓
producer/consumer runtime tests
    ↓
stack drift gates green
```

If a consumer implementation needs a new field before the canonical owner has merged it, keep the consumer PR blocked. Do not weaken the drift gate.

## Ownership Discovery

Inspect:

- `.mq/repo-contract.json`
- `schemas/vendored-contracts.json`
- the schema title / contract id
- contract tests in the likely owner
- stack architecture docs when ownership is ambiguous

Record the owner explicitly before editing more than one repository.

## Migration Workflow

### 1. Establish current truth

Capture:

- canonical repository and schema path
- consumer repository/schema path
- current contract id/version
- current producer behavior
- all known consumers
- backward-compatibility expectation

### 2. Change the canonical owner first

In the owner repository:

- make the smallest compatible schema change;
- add positive and negative contract tests;
- update an example if it helps prove the new field;
- update roadmap/decision documentation when the ownership or semantics changed;
- keep absence distinct from measured zero/false when that distinction matters.

### 3. Verify and merge the owner

Do not vendor from an unmerged side branch when the stack gate reads owner `main`.

Required evidence:

- owner PR head is green;
- owner merge commit is known;
- canonical file on owner `main` contains the intended contract.

### 4. Vendor exactly into consumers

The consumer copy must be derived from the merged canonical file, not rewritten by hand.

Prefer byte-identical content when the repository's gate expects exact parity.

Update:

- producer/consumer validation code;
- packaging manifests when schemas ship in artifacts;
- consumer tests;
- repo contract declarations where applicable.

### 5. Verify drift and behavior

Run repository-local tests and the stack contract/drift checks.

For mq-agent consumers, typical checks are:

```bash
python -m pytest -q
./release-check.sh
mq-agent stack contract-check
```

## Compatibility Rules

- Do not silently remove previously valid v1 fields.
- Optional fields remain optional unless a versioned breaking change is intentional.
- Do not backfill unknown measurements with zero.
- Preserve contract ids unless a real incompatible version boundary is required.
- A runtime implementation must not emit fields the canonical contract rejects.
- A consumer must not claim canonical parity until the canonical owner merge is visible.
- Widening an enum (for example a new `task_class`) is additive under the
  owner's versioning rule (mqobsidian DEC-006): old records stay valid. It still
  carries a forward cost, because an older closed-schema reader rejects the new
  value. Add a consumer test that shows the older reader counting the new record
  as invalid while still reading its own records.
- When a runtime keeps a list of accepted values next to the schema (for example
  `KNOWN_TASK_CLASSES`), update it in the same consumer PR. Otherwise the new
  value is silently rewritten to `unclassified`.

## Published Meaning and Pass-Through Payloads

- Do not change what an existing field means. When a field's semantics change
  (for example one `approval_id` that becomes two distinct approvals), write a
  new contract version and keep the old one readable through a dispatch on
  `schema`.
- Do not add keys to a payload that the command only passes through, least of
  all a content-addressed one such as `mq.review-receipt.v1`. Put the new data
  in an explicit envelope behind a flag (`{"execution": …, "review": <unchanged>}`)
  and keep the default output byte-identical.
- Check the owner before planning the change, not after the consumer PR is
  written. Incident: a plan to widen `mq.execution-outcome.v1` inside mq-agent
  would have failed the vendoring gate. The owner PR went first, and the
  consumer PR was opened with its vendoring gate expected red until that merge.

## Cross-Repo Safety

Use `mq-worktree-safe` for isolated local implementation and `mq-writing-plans` for multi-repo migrations.

For public repositories, use `mq-secrets-public-safe` before publishing generated or example data.

## Verification

A migration is complete only when all are true:

- canonical owner tests pass;
- owner PR is merged;
- consumer vendored copy matches canonical owner `main`;
- producer payload validates;
- consumers still accept historical valid payloads where promised;
- local release/contract gates pass;
- exact consumer PR head CI is green.

## Report Format

Return:

- contract id
- canonical owner
- owner merge commit
- consumer repositories
- compatibility impact
- files changed
- positive/negative tests added
- drift-gate result
- any consumer still pending
