# Stack Release Notes

Draft release notes from git commits since the last tag, per repo.

## Quick start

```bash
# Show unreleased commits for all repos
mq-agent stack release-notes

# Single repo
mq-agent stack release-notes --repo mq-agent

# Machine-readable
mq-agent stack release-notes --json
```

## How it works

For each mq-stack repo, `stack release-notes` reads:

1. The latest git tag (`git describe --tags --abbrev=0`)
2. Commits since that tag (`git log <tag>..HEAD --oneline --no-merges`)

If no tag exists the command falls back to the last 20 commits.

No API key required. No network calls.

## Example output

```text
────────────────── mq-stack Release Notes ──────────────────

mqlaunch  v1.0.0  (since v1.0.0)
  no unreleased commits

mq-agent  v1.9.0  (since v1.9.0)
  • abc1234 feat: add stack release-notes command
  • def5678 docs: update ROADMAP to v1.10.0

mq-mcp  v1.10.0  (since v1.10.0)
  no unreleased commits

✓ Most repos are up to date.
```

## JSON output

```bash
mq-agent stack release-notes --json
```

```json
[
  {
    "name": "mq-agent",
    "exists": true,
    "version": "1.9.0",
    "last_tag": "v1.9.0",
    "commits": [
      "abc1234 feat: add stack release-notes command"
    ],
    "has_changes": true
  },
  {
    "name": "mq-mcp",
    "exists": true,
    "version": "1.10.0",
    "last_tag": "v1.10.0",
    "commits": [],
    "has_changes": false
  }
]
```

Empty `commits` array + `has_changes: false` means the repo is at its latest tag.

## Typical workflow

```bash
mq-agent stack sweep              # update health scores
mq-agent stack report             # consolidated view
mq-agent stack alert              # regression check
mq-agent stack release-check      # release gate
mq-agent stack release-notes      # draft notes for unreleased work
```

`stack release-notes` always exits 0 — it is informational only.
Use `stack release-check` for gating.

## Companion commands

```bash
mq-agent stack release-check      # release gate (exit 1 on blocker)
mq-agent stack report             # score + trend + alert + ready
mq-agent stack alert              # regression check (exit 1 on drop)
```
