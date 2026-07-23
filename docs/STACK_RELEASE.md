# Stack Release

`mq-agent stack release` is the orchestrated single-repo release pipeline.

v1.14.0 closes the loop: the stack suite observes (`status`, `report`, `sweep`,
`history`), gates (`alert`, `release-check`, `contract-check`), remembers
(`truth-export`), and drafts (`release-notes`) — `stack release` makes it act.
A green release gate becomes the declared release path without guessing whether
the repo allows direct pushes.

---

## Command

```bash
mq-agent stack release --repo <name>             # dry-run (default): show the plan
mq-agent stack release --repo <name> --execute   # direct release or PR prepare
mq-agent stack release --repo <name> --version X.Y.Z \
  --finalize-pr <number> --approve                # finalize a merged release PR
```

Options:

```bash
--bump patch|minor|major   # version bump, default patch
--version X.Y.Z            # explicit target version (overrides --bump)
--json                     # machine-readable output, CI-friendly exit codes
```

---

## Release modes

Each repo declares `release_mode` in `.mq/repo-contract.json`:

| Mode | Plan and execute behavior |
| --- | --- |
| `direct` | Bump, sync, re-gate, commit, tag, push, push tag, truth export |
| `pull_request` | Bump, sync, re-gate, commit, push release branch, open draft PR, then stop at `AWAITING_MERGE` |
| `manual` | Block automation with an explicit policy reason |

Missing contracts, missing modes, and unknown modes also block. Dry-run and
execute use the same policy decision.

Both executable modes begin with the same gates: a clean `main`/`master`, at
least one unreleased commit, a valid target version, and the repo's own
release check. Version, contract, changelog, and declared release docs are
synchronized before the release commit.

### PR-mediated finalize

`pull_request` deliberately separates three approvals:

1. Prepare and open the draft release PR with `--execute`.
2. Review and merge the PR through GitHub.
3. Finalize the verified merge commit with `--finalize-pr <number> --approve`.

Finalize verifies the merged PR, base/head relationship, merge commit, version
surfaces, and tag absence before creating and pushing the annotated tag.
Nothing tags or pushes a tag before merge. Creating a GitHub Release remains a
separate release operation; finalize only establishes the verified Git tag.

---

## Safety model

* **Dry-run by default.** Without `--execute` nothing is touched — the
  command prints the plan (steps, version transition, warnings) and exits.
* **NO-GO refuses to run.** Blockers (dirty tree, off-main branch, no
  unreleased commits, missing VERSION/README, invalid target version, or
  release-mode policy) exit 1 before any mutation.
* **Abort on failure, no half-released repos.** A failed step aborts the
  run; the remaining steps are reported as `aborted`. File edits made before
  the release commit are rolled back (`git restore --staged --worktree`), so
  an aborted run leaves the repo exactly as it was.
* **Pushed means released.** If push succeeds but truth-export fails, the
  result reports `released: true` with a warning and exits 1 — the release
  happened; only the memory write needs a retry (`mq-agent stack truth-export`).

---

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Dry-run plan is GO, or executed release fully succeeded |
| 1 | NO-GO plan, failed step, or release succeeded but truth-export failed |

---

## JSON output

Dry-run returns the plan:

```bash
mq-agent stack release --repo repo-signal --bump minor --json | jq '.steps[].step'
```

Execute returns per-step status:

```bash
mq-agent stack release --repo repo-signal --execute --json | jq '{ok, released, tag, steps}'
```

For a PR-mediated repo, inspect the prepare state and PR URL:

```bash
mq-agent stack release --repo mq-agent --execute --json |
  jq '{state, release_mode, pull_request, steps}'
```

Do not run `stack release --all --execute --approve` blindly. Inspect the
read-only `--all --preflight --json` result first, then approve a separate,
reviewed release plan. A stack containing PR-mediated repos stops after PR
preparation and waits for merge.

---

## Tool registry

Registered as `stack_release` in `TOOL_REGISTRY` — dry-run by default;
`execute=True` follows the repo's declared release mode.
