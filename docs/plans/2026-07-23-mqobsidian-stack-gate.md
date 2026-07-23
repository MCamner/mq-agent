# MQobsidian Stack Gate Coverage Implementation Plan

## Goal

Keep the full-stack GitHub Actions workspace aligned with the repositories
required by `MQ_STACK_REPOS`.

## Owner repo

mq-agent

## Secondary repos

None.

## Architecture boundary

- mqobsidian owns context contracts, templates, generators, and published context surfaces.
- mq-agent owns planning, workflow routing, task decomposition, and agent handoff.
- mq-mcp owns execution tools, tool safety, and runtime boundaries.
- mq-hal owns status, operator summaries, release/runbook views.
- repo-signal owns publish readiness, security/readiness scoring, and repo health checks.

## Non-goals

- Release preparation, execution, finalization, tagging, or version changes.
- Changes to stack membership or contract-check behavior.

## Approval gates

- Before file writes: approved in task.
- Before commit: approved in task.
- Before push/merge: push and draft PR approved; merge not approved.
- Before deletion/settings changes: yes.

## Test gates

- `uv run pytest -q tests/test_ci_stack_gate.py`
- `uv run pytest -q`
- `uv run ruff check .`
- `./scripts/markdownlint.sh`
- `git diff --check`

## Rollback

Revert the fix commit; no release state or external runtime state is changed.

### Task 1: Add workflow coverage regression

**Purpose:** Detect any configured stack repository missing from the full-stack
checkout or home-layout link steps.

**Files:**

- Create: `tests/test_ci_stack_gate.py`
- Read-only reference: `mq_agent/tools/stack_tools.py`
- Read-only reference: `.github/workflows/mq-stack-gate.yml`

**Steps:**

1. Derive expected checkout and link names from `MQ_STACK_REPOS`.
2. Parse the workflow's checkout paths and home-layout links.
3. Assert exact coverage and explicit `mqobsidian` inclusion.
4. Run the focused test and confirm it fails before the workflow fix.

**Expected result:** The regression test fails because `mqobsidian` is missing.

**Commit suggestion:** `fix(ci): include mqobsidian in stack gate checkout`

### Task 2: Provision mqobsidian in the full-stack gate

**Purpose:** Make the main/nightly/manual full-stack workspace match the
contract-check repo set.

**Files:**

- Modify: `.github/workflows/mq-stack-gate.yml`

**Steps:**

1. Add an `MCamner/mqobsidian` checkout using the existing pattern.
2. Add the `$HOME/mqobsidian` symlink using the existing pattern.
3. Run all test gates and review the final diff.

**Expected result:** Workflow coverage and repository tests pass without
touching release/version surfaces.

**Commit suggestion:** `fix(ci): include mqobsidian in stack gate checkout`
