# MQ Stack Version Sync Implementation Plan

## Goal

Synchronize local MQ repository branches and tags with GitHub while preserving every local commit and uncommitted change, then reconcile published release metadata.

## Owner repo

mq-agent

## Secondary repos

macos-scripts, mq-mcp, mqobsidian, repo-signal, mq-image-analyze, mq-ums, mq-hal

## Architecture boundary

- mqobsidian owns context contracts, templates, generators, and published context surfaces.
- mq-agent owns planning, workflow routing, task decomposition, and agent handoff.
- mq-mcp owns execution tools, tool safety, and runtime boundaries.
- mq-hal owns status, operator summaries, release/runbook views.
- repo-signal owns publish readiness, security/readiness scoring, and repo health checks.

## Non-goals

- No source-code or generated project-file changes.
- No deletion of feature branches or user work.
- No force-pushes or rewriting GitHub history.
- No new software versions or tags.

## Approval gates

- Before file writes: approved by the user's `fixa` request for this plan only.
- Before commit: yes; this plan is not committed automatically.
- Before push/merge: yes; no source branch will be pushed or merged automatically.
- Before deletion/settings changes: yes; conflicting local tag replacement requires the execution approval after this plan.

## Test gates

- `git status --porcelain` before and after each repository operation.
- `git rev-list --left-right --count main...origin/main` must end as `0 0`.
- Current tracking branches must be `0 0`, except a preserved intentional local commit.
- Local and GitHub object IDs must match for `mq-ums:v0.1.4` and `mq-hal:v1.2.0` after reconciliation.
- `gh release view v1.18.0 -R MCamner/mq-agent` must confirm the intended latest release state.

## Rollback

- Before moving any branch or tag, create timestamped refs under `refs/mq-backup/2026-07-15/`.
- Restore a branch with `git branch -f <branch> refs/mq-backup/2026-07-15/<repo>/<branch>`.
- Restore a tag with `git tag -f <tag> refs/mq-backup/2026-07-15/<repo>/tag/<tag>`.
- Preserve `mq-mcp/learn_engine/memory/lessons.jsonl` in place; stop on any conflict.

### Task 1: Capture immutable local backups

**Purpose:** Preserve divergent branches, conflicting tags, and the dirty mq-mcp state before synchronization.

**Files:**

- Read-only reference: Git refs and working trees in all eight MQ repositories.
- Read-only reference: `mq-mcp/learn_engine/memory/lessons.jsonl`.

**Steps:**

1. Record current branch, HEAD, upstream, dirty paths, `main`, `origin/main`, and relevant tag objects.
2. Create namespaced backup refs for every ref that will move.
3. Export the mq-mcp working-tree diff to `/tmp` as a secondary recovery artifact.
4. Verify all backup refs resolve.

**Commands:**

```bash
git update-ref refs/mq-backup/2026-07-15/<repo>/<name> <object-id>
git diff --binary -- learn_engine/memory/lessons.jsonl
git show-ref refs/mq-backup/2026-07-15/<repo>/<name>
```

**Expected result:**
Every local-only state has a resolvable backup before a branch or tag moves.

**Commit suggestion:**
No commit.

### Task 2: Synchronize local main refs

**Purpose:** Make each local `main` match its fetched `origin/main` without discarding local-only commits.

**Files:**

- Modify: local Git refs only.

**Steps:**

1. Fast-forward `macos-scripts`, `mqobsidian`, and `repo-signal` local `main` refs.
2. Move the backed-up divergent `main` refs in `mq-mcp`, `mq-image-analyze`, `mq-ums`, and `mq-hal` to `origin/main`; their local-only commits remain reachable from feature branches and backup refs.
3. Leave `mq-agent` unchanged because it is already synchronized.
4. Verify `main...origin/main` is `0 0` everywhere.

**Commands:**

```bash
git branch -f main origin/main
git rev-list --left-right --count main...origin/main
```

**Expected result:**
All local `main` refs exactly match GitHub while local-only commits remain recoverable.

**Commit suggestion:**
No commit.

### Task 3: Reconcile active tracking branches safely

**Purpose:** Update clean active branches without rewriting shared history or losing the mq-mcp working change.

**Files:**

- Modify: local Git refs and working tree only where fast-forward is possible.
- Preserve: `mq-mcp/learn_engine/memory/lessons.jsonl`.

**Steps:**

1. Fast-forward the mq-mcp active branch by one commit while preserving its working-tree modification.
2. Leave branches that are already synchronized unchanged.
3. Do not rebase branches that diverge from `origin/main`; report them as preserved feature work.
4. Stop if the mq-mcp update conflicts with the modified file.

**Commands:**

```bash
git merge --ff-only @{upstream}
git status --porcelain
git rev-list --left-right --count HEAD...@{upstream}
```

**Expected result:**
Tracking branches are current where a safe fast-forward exists; no user content changes.

**Commit suggestion:**
No commit.

### Task 4: Reconcile conflicting local tags

**Purpose:** Make fetched release tags match GitHub while retaining recoverable references to the conflicting local objects.

**Files:**

- Modify: local tag refs `mq-ums:v0.1.4` and `mq-hal:v1.2.0`.

**Steps:**

1. Verify backup refs for both current local tag objects.
2. Fetch the two tags explicitly with force from GitHub.
3. Compare local ref object IDs with the GitHub API.

**Commands:**

```bash
git fetch origin +refs/tags/<tag>:refs/tags/<tag>
git rev-parse <tag>
gh api repos/MCamner/<repo>/git/ref/tags/<tag>
```

**Expected result:**
The local release tags match GitHub and the prior objects remain under backup refs.

**Commit suggestion:**
No commit.

### Task 5: Reconcile mq-agent latest-release metadata

**Purpose:** Resolve the mismatch between the existing `v1.18.0` tag/package version and GitHub's latest release marker `v1.13.0`.

**Files:**

- Read-only reference: `pyproject.toml`, changelog/release notes, and GitHub releases.
- Modify: GitHub release metadata only if the repository's release convention confirms `v1.18.0` should be published.

**Steps:**

1. Inspect releases `v1.14.0` through `v1.18.0` and the repository release workflow.
2. If `v1.18.0` already has a release, mark it latest.
3. If only the tag exists, create a GitHub release from the existing tag using repository-consistent notes.
4. Do not create or move a tag.
5. Verify GitHub reports `v1.18.0` as latest.

**Commands:**

```bash
gh release list -R MCamner/mq-agent
gh release view v1.18.0 -R MCamner/mq-agent
gh release create v1.18.0 -R MCamner/mq-agent --verify-tag --latest
```

**Expected result:**
GitHub's latest release matches the already-published `v1.18.0` tag and package version, or the mismatch is left unchanged with a documented release-policy reason.

**Commit suggestion:**
No commit.

### Task 6: Run final stack audit

**Purpose:** Produce evidence that synchronization succeeded and identify deliberately preserved feature work.

**Files:**

- Read-only reference: all eight MQ repositories.

**Steps:**

1. Fetch branches and tags again.
2. Verify branch counts, dirty paths, tag objects, package versions, and latest releases.
3. Confirm backup refs exist.
4. Report exact remaining deviations and why they were preserved.

**Commands:**

```bash
git status -sb
git rev-list --left-right --count main...origin/main
git rev-list --left-right --count HEAD...@{upstream}
git show-ref refs/mq-backup/2026-07-15
gh release list -R MCamner/<repo>
```

**Expected result:**
All `main` refs and release tags are synchronized; any remaining deviations are intentional, backed up, and explicitly reported.

**Commit suggestion:**
No commit.
