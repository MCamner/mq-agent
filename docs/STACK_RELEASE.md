# Stack Release

`mq-agent stack release` is the orchestrated single-repo release pipeline.

v1.14.0 closes the loop: the stack suite observes (`status`, `report`, `sweep`,
`history`), gates (`alert`, `release-check`, `contract-check`), remembers
(`truth-export`), and drafts (`release-notes`) — `stack release` makes it act.
A green release gate becomes an actual release without manual per-repo steps.

---

## Command

```bash
mq-agent stack release --repo <name>             # dry-run (default): show the plan
mq-agent stack release --repo <name> --execute   # apply the release
```

Options:

```bash
--bump patch|minor|major   # version bump, default patch
--version X.Y.Z            # explicit target version (overrides --bump)
--json                     # machine-readable output, CI-friendly exit codes
```

---

## Pipeline

An executed release runs these steps, in order, aborting on the first failure:

1. **Gate** — `release-check` for the repo must pass, plus stricter
   release-time rules: clean working tree, on `main`/`master`, and at least
   one unreleased commit since the last tag.
2. **bump-version** — updates `VERSION` / `version.txt` and the
   `pyproject.toml` `version` field.
3. **sync-contract** — updates `version` in `.mq/repo-contract.json` so the
   contract gate stays READY after the release.
4. **update-changelog** — inserts a `## [vX.Y.Z]` section drafted from the
   commits since the last tag (the `release-notes` draft), under
   `## [Unreleased]` when present.
5. **commit** — `release: vX.Y.Z`.
6. **tag** — `vX.Y.Z`.
7. **push** + **push-tag**.
8. **truth-export** — writes the stack truth note to mqobsidian, so the
   release lands in durable memory.

---

## Safety model

* **Dry-run by default.** Without `--execute` nothing is touched — the
  command prints the plan (steps, version transition, warnings) and exits.
* **NO-GO refuses to run.** Blockers (dirty tree, off-main branch, no
  unreleased commits, missing VERSION/README, invalid target version) exit 1
  before any mutation.
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

---

## Tool registry

Registered as `stack_release` in `TOOL_REGISTRY` — dry-run by default;
`execute=True` applies the release.
