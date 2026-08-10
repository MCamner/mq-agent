# Release Cockpit v1.25 Implementation Plan

## Goal

Deliver a read-only `mq-agent ship` operator surface that resolves one release
state, explains blockers, recommends one next action, and exposes release proof
and audit evidence without changing the existing release engine.

## Owner repo

mq-agent

## Secondary repos

None.

## Architecture boundary

- `mq-agent` owns release-state aggregation, operator guidance, and CLI output.
- Existing `stack release` planning, policy, preflight, prepare, and finalize
  functions remain the release engine and source of release policy.
- Git and GitHub are read-only evidence sources for all `ship` commands.
- `mq-hal` and `mqlaunch` may consume the JSON contract later; this change does
  not add or duplicate their presentation logic.
- `mqobsidian` remains durable memory, not live release truth.

## Non-goals

- No automatic prepare, merge, finalize, tag, push, or publication.
- No changes to existing `stack release` execution behavior.
- No version bump, commit, push, tag, or GitHub Release creation.
- No unrelated cleanup.

## Approval gates

- Before file writes: approved by the request to complete v1.25.
- Before commit: yes; not included in this plan.
- Before push/merge: yes; not included in this plan.
- Before deletion/settings changes: yes; not included in this plan.

## Test gates

- `.venv/bin/pytest -q -p no:cacheprovider tests/test_release_cockpit.py`
- `.venv/bin/pytest -q -p no:cacheprovider`
- `.venv/bin/ruff check --no-cache .`
- `.venv/bin/mypy mq_agent`
- `./scripts/check-docs-consistency.sh`
- `git diff --check`

## Rollback

- Revert the new cockpit module, schema, tests, documentation, and the small CLI
  registration change. Existing `stack release` code remains untouched.

### Task 1: Define the release-state and evidence contract

**Purpose:** Make state precedence, blocker codes, proof fields, and next-action
selection deterministic and independently testable.

**Files:**

- Create: `mq_agent/tools/release_cockpit.py`
- Create: `schemas/mq_release_cockpit.schema.json`
- Create: `tests/test_release_cockpit.py`
- Modify: `pyproject.toml`
- Read-only reference: `mq_agent/tools/stack_release.py`
- Read-only reference: `mq_agent/tools/stack_tools.py`

**Steps:**

1. Add failing tests for all nine states and their precedence.
2. Build a read-only evidence collector with injectable Git/GitHub runners.
3. Map bounded blocker codes and exactly one next action per state.
4. Validate stable JSON payloads against the packaged schema.
5. Run the focused test gate.

**Expected result:** Every snapshot resolves to exactly one documented state;
partial or unavailable evidence cannot produce a green result.

**Commit suggestion:**

`feat(ship): add release cockpit state contract`

### Task 2: Add status, proof, and audit CLI commands

**Purpose:** Expose the contract as a concise operator surface with human/JSON
parity and meaningful exit codes.

**Files:**

- Modify: `mq_agent/main.py`
- Modify: `tests/test_release_cockpit.py`

**Steps:**

1. Register `ship` and add `status`, `proof`, and `audit`.
2. Keep all commands read-only and accept a repository path plus optional target.
3. Render state, evidence, blockers, and one next action.
4. Return non-zero from audit when evidence is incomplete or blocking.
5. Run focused and regression tests.

**Expected result:** All required v1.25 commands and `--json` variants work
without invoking release mutations.

**Commit suggestion:**

`feat(cli): expose read-only ship cockpit`

### Task 3: Synchronize operator documentation and roadmap

**Purpose:** Make `ship` the documented operator surface and retain `stack
release` as the lower-level engine.

**Files:**

- Create: `docs/RELEASE_COCKPIT.md`
- Modify: `README.md`
- Modify: `docs/COMMAND_SURFACE.md`
- Modify: `docs/ROADMAP.md`
- Modify: `ROADMAP.md`
- Modify: `docs/index.html`

**Steps:**

1. Document commands, state meanings, evidence limitations, and exit behavior.
2. Add discoverable links to README, command reference, and Pages.
3. Mark only implemented v1.25 items complete.
4. Run documentation consistency and diff checks.

**Expected result:** Public and root roadmap surfaces agree, and operators can
find the cockpit without confusing it with the release engine.

**Commit suggestion:**

`docs(ship): document release cockpit workflow`
