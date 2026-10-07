---
name: mq-state-recovery-audit
description: Use when reviewing or changing MQ local-state inventory, snapshot, verification, restore, disaster recovery, allowlists, hashes, or secret/privacy boundaries.
---

# MQ State Recovery Audit

Use this skill to prove that local MQ runtime state can be inventoried, snapshotted, verified, and restored without becoming a generic backup of private machine state.

## When to use

- Reviewing `mq-agent state inventory`
- Changing snapshot or restore logic
- Adding a new allowlisted state component
- Testing disaster recovery or portability
- Investigating snapshot hash/manifest failures
- Auditing whether credentials, private paths, or free-form memory can leak into snapshots

## When not to use

- General repository backups
- Durable semantic-memory promotion policy
- Feedback policy activation — use `mq-feedback-control-plane`
- Shared contract migration — use `mq-contract-owner-migration`

## Evals

### Should trigger

- "audit mq-agent state restore before we trust it"
- "add review receipts to the portable snapshot"
- "prove tampered state snapshots fail verification"
- "what does mq-agent state intentionally exclude?"
- "test recovery onto a clean machine"
- "make restore delete files that are not in the snapshot" → trigger and refuse that unsafe default

### Should not trigger

- "backup my whole home directory" → outside MQ state-recovery scope
- "promote this session to durable memory" → use the memory promotion flow
- "change canonical execution outcome schema" → use `mq-contract-owner-migration`
- "CI failed" → use `ci-diagnosis`

## Recovery Invariants

- Snapshot content is allowlisted, never "copy everything under state".
- Manifest paths are logical/portable, not private absolute machine paths.
- Every copied file has size and cryptographic hash evidence.
- Verification fails on tampering, missing declared files, or unexpected undeclared files.
- Restore writes only manifest-declared allowlisted files.
- Restore must not delete unrelated current state by default.
- Credentials, environment variables, secret stores, generic free-form notes, and remote vector-store contents stay excluded unless a separately reviewed contract says otherwise.
- Snapshot creation and verification are read-safe operations.
- Restore is an explicit write operation and requires operator approval at the CLI boundary.
- Recovery evidence must distinguish "not present" from "verified empty".

## Files To Inspect

- `mq_agent/tools/state_snapshot.py`
- `schemas/state_snapshot.schema.json`
- `tests/test_state_snapshot.py`
- `docs/COMMAND_SURFACE.md`
- `docs/SAFETY_CONTRACT.md`

## Audit Workflow

### 1. Inventory the allowlist

```bash
mq-agent state inventory --json
```

Confirm every included component has a concrete recovery purpose.

For each component record:

- source location class
- data sensitivity
- portability
- whether content is sanitized
- whether another system is the canonical source

### 2. Create a snapshot

```bash
mq-agent state snapshot <snapshot-dir> --approve --json
```

Inspect the manifest, not only the exit code.

Confirm:

- schema id;
- relative manifest paths;
- file counts;
- byte sizes;
- SHA-256 values;
- exclusions.

### 3. Verify before restore

```bash
mq-agent state verify <snapshot-dir> --json
```

Verification must fail closed on:

- content tamper;
- size mismatch;
- undeclared extra file;
- path traversal;
- malformed manifest;
- contract validation failure.

### 4. Dry recovery test

Use an isolated temporary state root.

Seed known current files, restore the snapshot with explicit approval, and prove:

- declared files recover exactly;
- unrelated files survive;
- no excluded state appears;
- repeated verification remains deterministic.

### 5. Adversarial mutation tests

At minimum test:

- one byte changed after snapshot;
- extra file inserted into snapshot;
- declared file removed;
- path changed to escape the destination;
- private absolute path inserted into metadata;
- credential-like content in any newly allowlisted source;
- restore attempted without approval.

## Change Rules

When adding a component to the allowlist:

1. Explain why it is needed for recovery.
2. Identify its canonical owner.
3. Add public-safe/private-path tests.
4. Add tamper/restore coverage.
5. Update the state snapshot schema only if the manifest contract changes.
6. Use `mq-contract-owner-migration` if that schema becomes shared across repositories.

Use `mq-secrets-public-safe` whenever snapshot examples or fixtures may cross a public boundary.

## Verification

```bash
python -m pytest tests/test_state_snapshot.py -q
python -m pytest -q
./release-check.sh
```

For disaster-recovery claims, include an isolated restore test rather than inferring success from snapshot creation alone.

## Report Format

Return:

- included components
- excluded components
- manifest/hash status
- privacy/secret findings
- tamper-test result
- restore-test result
- unrelated-state preservation result
- unresolved recovery gaps
- safe-to-use verdict: yes/no/conditional
