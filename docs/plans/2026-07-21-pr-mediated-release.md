# PR-Mediated Release Path Implementation Plan

## Goal

Add a safe two-stage release path for repositories that declare
`release_mode: "pull_request"`, without weakening direct or manual release
guards.

## Owner repo

mq-agent

## Secondary repos

- macos-scripts (read-only validation target)
- mqobsidian (read-only validation target)

## Architecture boundary

- mqobsidian owns context contracts, templates, generators, and published context surfaces.
- mq-agent owns planning, workflow routing, task decomposition, and agent handoff.
- mq-mcp owns execution tools, tool safety, and runtime boundaries.
- mq-hal owns status, operator summaries, release/runbook views.
- repo-signal owns publish readiness, security/readiness scoring, and repo health checks.
- Each repository owns its version surfaces and `release-check.sh`.
- GitHub owns branch protection and PR merge state; mq-agent must query it explicitly.

## Non-goals

- Do not execute a real release while implementing or testing this slice.
- Do not merge release PRs automatically.
- Do not create tags before a release PR is merged.
- Do not infer candidate mqobsidian contract ownership.
- Do not change contracts, versions, tags, or release configuration in secondary repos.
- Do not weaken `manual` mode or treat a missing/unknown mode as `direct`.

## Approval gates

- Before file writes: approved for this plan only; implementation requires plan approval.
- Before commit: yes.
- Before push/merge: yes.
- Before deletion/settings changes: yes; none planned.
- Before any real release/tag: separate explicit approval; excluded from this plan.

## Design decision

Use an explicit two-stage state machine for `pull_request` repositories:

1. **Prepare:** create a deterministic release branch, update owned version
   surfaces, re-run the repository release check, commit, push the branch, and
   open a draft PR. Do not tag and do not push `main`.
2. **Finalize:** only after GitHub reports that exact release PR merged into the
   expected base commit, create and push the annotated tag for the already
   merged release commit, then export stack truth.

`--all --execute --approve` may prepare PR-mode repositories, but it must not
direct-release other repositories in the same invocation while any PR-mode
repository is awaiting merge. This avoids an avoidable partial stack release.
The result must report `PR_OPENED`/`AWAITING_MERGE` rather than `RELEASED`.

## Test gates

- `uv run pytest tests/test_stack_release.py -q`
- `uv run ruff check mq_agent/tools/stack_release.py mq_agent/main.py tests/test_stack_release.py`
- `git diff --check`
- `uv run mq-agent stack release --all --preflight --json`
- Full suite before commit: `uv run pytest -q`

## Rollback

- Before commit: `git restore -- mq_agent/tools/stack_release.py mq_agent/main.py tests/test_stack_release.py README.md`
- After commit but before merge: revert the implementation commit; do not delete tags because tests must never create remote tags.
- A failed prepare restores uncommitted version-surface edits and returns to the starting branch.
- A pushed release branch or opened draft PR is reported for manual closure; it is never force-pushed or deleted automatically.

### Task 1: Lock the PR release state machine with tests

**Purpose:** Define the refusal and transition rules before implementation.

**Files:**

- Modify: `tests/test_stack_release.py`
- Read-only reference: `mq_agent/tools/stack_release.py`
- Read-only reference: `mq_agent/main.py`

**Steps:**

1. Add failing tests for `pull_request` prepare behavior.
2. Prove no tag or direct-main push occurs during prepare.
3. Prove an existing matching PR is reused rather than duplicated.
4. Prove failure restores the starting branch and uncommitted edits.
5. Prove `manual`, missing, and unknown modes still block.
6. Prove mixed direct/PR stacks stop in `AWAITING_MERGE` without directly releasing later repos.

**Commands:**

```bash
uv run pytest tests/test_stack_release.py -q
```

**Expected result:**

New tests fail only because the PR-mediated path is not implemented.

**Commit suggestion:**

`test(stack): define PR-mediated release transitions`

### Task 2: Implement PR preparation without tagging

**Purpose:** Safely prepare a release change for branch-protected repositories.

**Files:**

- Modify: `mq_agent/tools/stack_release.py`
- Modify: `tests/test_stack_release.py`

**Steps:**

1. Add a deterministic release branch name derived from repo and target tag.
2. Re-verify clean tree, main branch, upstream sync, and release mode immediately before mutation.
3. Create the release branch, update version/contract/changelog surfaces, and run the post-bump release gate.
4. Commit and push only the release branch.
5. Open or reuse a draft PR through `gh`; record PR number, URL, head, base, target version, and expected merge base.
6. Never create or push a tag in prepare mode.
7. Restore the starting checkout on success, command failure, `INT`, and `TERM` where process handling permits.

**Commands:**

```bash
uv run pytest tests/test_stack_release.py -q
uv run ruff check mq_agent/tools/stack_release.py tests/test_stack_release.py
```

**Expected result:**

PR-mode execution returns `PR_OPENED` or `AWAITING_MERGE`, leaves the local
checkout on its starting branch, and creates no tag.

**Commit suggestion:**

`feat(stack): prepare releases through pull requests`

### Task 3: Add explicit post-merge finalization

**Purpose:** Tag only the exact release commit after GitHub confirms the release PR was merged.

**Files:**

- Modify: `mq_agent/tools/stack_release.py`
- Modify: `mq_agent/main.py`
- Modify: `tests/test_stack_release.py`

**Steps:**

1. Add an explicit finalize operation; do not infer finalization from ordinary dry-run or execute calls.
2. Fetch remote state and require clean, synced `main`.
3. Verify the recorded PR is merged, its base is the expected default branch, its head matches the release branch, and the merged commit contains the expected version surfaces.
4. Refuse if the tag exists locally or remotely at a different commit.
5. Create and push the annotated tag, then export stack truth.
6. Make retry behavior idempotent when the correct tag already points at the verified merge commit.

**Commands:**

```bash
uv run pytest tests/test_stack_release.py -q
uv run mq-agent stack release --help
```

**Expected result:**

No tag can be created until the matching release PR is verified as merged; a
safe retry reports the already-finalized state without rewriting anything.

**Commit suggestion:**

`feat(stack): finalize merged release pull requests`

### Task 4: Wire multi-repo orchestration and operator output

**Purpose:** Make `--all --execute --approve` route by declared release mode without creating partial releases accidentally.

**Files:**

- Modify: `mq_agent/tools/stack_release.py`
- Modify: `mq_agent/main.py`
- Modify: `tests/test_stack_release.py`
- Modify: `README.md` only if the public command contract changes

**Steps:**

1. Classify all READY repos by release mode before the first mutation.
2. Keep `manual`, missing, and unknown modes blocked.
3. If any PR-mode repo needs preparation, prepare those PRs and report `AWAITING_MERGE`; do not direct-release other repos in that invocation.
4. Preserve fail-fast behavior and explicit `--approve`.
5. Render PR URLs and the exact finalize command in JSON and terminal output.
6. Run targeted and full verification without executing a real release.

**Commands:**

```bash
uv run pytest tests/test_stack_release.py -q
uv run pytest -q
uv run ruff check mq_agent/tools/stack_release.py mq_agent/main.py tests/test_stack_release.py
git diff --check
uv run mq-agent stack release --all --preflight --json
```

**Expected result:**

The multi-repo command produces reviewable release PRs for protected repos,
does not tag prematurely, and never mixes pending PR transitions with direct
releases in one invocation.

**Commit suggestion:**

`feat(stack): route protected releases through pull requests`
