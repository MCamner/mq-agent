# Post-v1.25 Roadmap Sync Implementation Plan

## Goal

Synchronize the canonical and public mq-agent roadmaps after v1.25.1 and make
v1.26.0 Stack Compatibility Gate the single active next release.

## Owner repo

mq-agent

## Secondary repos

None.

## Architecture boundary

- `mq-agent` owns these committed roadmap surfaces and the compatibility-gate
  orchestration plan.
- Other MQ repositories remain owners of their dependency declarations and
  machine-readable contracts.
- This change documents direction only; it adds no compatibility implementation.

## Non-goals

- No product-code, schema, CLI, CI, or release changes.
- No implementation of `ship` write wrappers.
- No resolution of upstream `repo-signal` or `mq-mcp` evidence contracts.

## Approval gates

- Before file writes: approved by the request to fix the roadmap steps.
- Before commit: yes; not included in this plan.
- Before push/merge: yes; not included in this plan.
- Before deletion/settings changes: yes; not included in this plan.

## Test gates

- `./scripts/check-docs-consistency.sh`
- `./scripts/markdownlint.sh`
- `git diff --check`

## Rollback

- Revert this documentation-only change; runtime and release artifacts are
  unaffected.

### Task 1: Close the v1.25 release record

**Purpose:** Replace stale v1.24/v1.25 future wording with verified release
facts for v1.25.0 and v1.25.1.

**Files:**

- Modify: `ROADMAP.md`
- Modify: `docs/ROADMAP.md`
- Read-only reference: `VERSION`
- Read-only reference: `CHANGELOG.md`

**Steps:**

1. Set current released version to v1.25.1.
2. Mark v1.25.0 and v1.25.1 released.
3. Close the final v1.25 definition-of-done gate.
4. Move optional `ship` write wrappers out of the completed milestone.

**Expected result:** Neither roadmap calls v1.25 unreleased or next.

### Task 2: Promote v1.26 compatibility work

**Purpose:** Establish one explicit next release and keep its ownership and
phase order discoverable on both roadmap surfaces.

**Files:**

- Modify: `ROADMAP.md`
- Modify: `docs/ROADMAP.md`

**Steps:**

1. Rename the P1 initiative to v1.26.0 Stack Compatibility Gate.
2. Add a concise public v1.26 scope and delivery order.
3. Keep the detailed phase plan canonical in the root roadmap.
4. Record `ship` write wrappers and upstream evidence ingestion as deferred.

**Expected result:** Both roadmaps identify v1.26.0 as the next release.

### Task 3: Separate active roadmap from history

**Purpose:** Stop completed and superseded release details from reading as
active planned work.

**Files:**

- Modify: `ROADMAP.md`
- Modify: `docs/ROADMAP.md`

**Steps:**

1. Rename misleading planned/history headings.
2. Add explicit archive and deferred-work boundaries.
3. Run documentation and whitespace gates.

**Expected result:** Active, deferred, and historical work are visibly distinct.
