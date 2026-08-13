# MQ Stack Contract Gate

Validates that every repo in the MQ stack declares and maintains a contract manifest.
No API key required. Exits 1 if any repo is BLOCKED or DRIFT.

## Quick start

```bash
mq-agent stack contract-check
mq-agent stack contract-check --json
```

## How it works

For each repo (excluding `mqobsidian`), the gate checks:

| Check | Failure status |
| --- | --- |
| Repo exists locally | BLOCKED |
| `VERSION` file present | BLOCKED |
| `README.md` present | BLOCKED |
| `.mq/repo-contract.json` exists | DRIFT |
| Contract JSON is valid | BLOCKED |
| All required fields present | BLOCKED |
| `contract.version` == `VERSION` file | DRIFT |
| Uncommitted changes or non-main branch | REVIEW |

Status precedence: **BLOCKED > DRIFT > REVIEW > READY**

The command exits 1 if any repo is BLOCKED or DRIFT. REVIEW does not fail the gate.

## Status meanings

* **READY** — contract manifest present, version synced, clean working tree on main.
* **REVIEW** — contract valid but has warnings (uncommitted changes, non-main branch). Does not fail the gate.
* **DRIFT** — contract missing or version not synced with `VERSION` file. Fails the gate.
* **BLOCKED** — hard error: repo not found, no VERSION, no README, invalid JSON, or missing required fields. Fails the gate.
* **SKIPPED** (CI mode only) — repo not present in the CI workspace. Never fails the gate.

## Contract file

Each MQ repo must have `.mq/repo-contract.json`:

```json
{
  "repo": "mq-agent",
  "role": "orchestrator",
  "version": "1.12.0",
  "status": "active",
  "contracts": ["stack_sweep.v1", "contract_gate.v1"],
  "next_focus": ""
}
```

Required fields: `repo`, `role`, `version`, `status`, `contracts`.

**`version` must be kept in sync with the root `VERSION` file.** When you bump VERSION, also update `.mq/repo-contract.json`.

Schema: [`schemas/mq_stack_repo_contract.schema.json`](../schemas/mq_stack_repo_contract.schema.json)

## Optional: `compatibility`

A repo may declare its machine-readable compatibility boundary. The field is
optional and existing contracts stay valid without it.

```json
{
  "compatibility": {
    "protocols": { "mcp_api": "1.x-fastmcp" },
    "dependencies": { "mcp": ">=1.27.1,<2" },
    "produces": ["mq-mcp.tools.v1"],
    "consumes": ["mq.feedback.v1"]
  }
}
```

`mq-agent stack compatibility` reads it and distinguishes two states:

| State | Finding | Blocks release |
|---|---|---|
| No `compatibility` block | `MQC009_COMPATIBILITY_METADATA_MISSING` (WARN) | No |
| Block contradicts `pyproject.toml` | `MQC011_DECLARED_DEPENDENCY_MISMATCH` (FAIL) | Yes |
| Range allows a major the protocol track excludes | `MQC012_PROTOCOL_CONTRADICTS_RANGE` (FAIL) | Yes |

Missing metadata is expected during rollout and never blocks. Metadata that
disagrees with the repo's own dependency declaration does block — a contract
that lies is worse than no contract.

`dependencies` is compared as a normalised specifier set, so `>=1.27.1,<2` and
`<2,>=1.27.1` are treated as the same boundary.

### `import_probes`

A repo may declare the statements that prove its contract still holds against a
freshly resolved dependency:

```json
{
  "compatibility": {
    "import_probes": { "mcp": "from mcp.server.fastmcp import FastMCP" }
  }
}
```

Any Python statement works, so a repo can smoke its own contract rather than
only its imports. Repos that declare nothing get the default probe above;
declaring an empty object opts out.

## What blocks merge and release

`mq-agent stack compatibility` maps its verdict onto exit codes:

| Status | Exit | Meaning | Blocks |
|---|---|---|---|
| `PASS` | 0 | Everything assessed, nothing wrong | No |
| `SKIPPED` | 0 | Nothing to assess | No |
| `WARN` | 0, or 1 with `--strict` | A real observation that is non-blocking during rollout | No |
| `FAIL` | 2 | A proven incompatibility | Yes |
| `UNAVAILABLE` | 3 | The check could not be run | Yes, in CI |
| — | 130 | Interrupted before a verdict | — |

Every finding carries `blocks_release`, and only `FAIL` findings set it. WARN
and UNAVAILABLE never block on their own.

**Where that is enforced today:** the push-to-`main` job and the nightly job in
`.github/workflows/mq-stack-gate.yml`. `blocks_release` is the machine-readable
signal; `mq-agent stack release-check` and the release cockpit do not yet read
it, so a FAIL fails CI on `main` rather than refusing a release. Wiring it into
the release gate is Phase 6.

`UNAVAILABLE` deserves the emphasis: it is not a pass. A missing sibling repo
locally is expected and harmless, but an explicitly requested `--fresh-resolve`
that could not reach the registry has assessed nothing, and the nightly job
fails on it deliberately.

| Finding | Severity | Blocks release |
|---|---|---|
| `MQC002_CONTRACT_MISSING` | WARN | No |
| `MQC003_CONTRACT_INVALID` | WARN | No |
| `MQC005_DECLARED_RANGE_UNBOUNDED` | WARN | No |
| `MQC006_LOCKED_OUTSIDE_DECLARED` | FAIL | Yes |
| `MQC007_DECLARED_RANGES_DISJOINT` | FAIL | Yes |
| `MQC008_PROTOCOL_TRACK_MISMATCH` | WARN, or FAIL when the repos are wired together | Only as FAIL |
| `MQC009_COMPATIBILITY_METADATA_MISSING` | WARN | No |
| `MQC011_DECLARED_DEPENDENCY_MISMATCH` | FAIL | Yes |
| `MQC012_PROTOCOL_CONTRADICTS_RANGE` | FAIL | Yes |
| `MQC013_CONTRACT_UNPRODUCED` | WARN | No |
| `MQC015_RESOLVED_DIFFERS_FROM_LOCKED` | WARN | No |
| `MQC016_IMPORT_PROBE_FAILED` | FAIL | Yes |
| `MQC017_RESOLVE_CONFLICT` | FAIL | Yes |
| `MQC001`, `MQC004`, `MQC010`, `MQC014` | UNAVAILABLE | No, but never green |

Finding codes are append-only within `mq.stack-compatibility.v1`.

## Where the gate runs

* **Pull requests** — not run. Only the mq-agent checkout exists there, so
  every sibling would report `UNAVAILABLE` and the gate would say nothing.
* **Push to `main`** — the static check, with every stack repo checked out.
* **Nightly and manual dispatch** — the static check plus
  `--fresh-resolve`, which needs a package registry.

```bash
mq-agent stack compatibility                  # declared and locked versions
mq-agent stack compatibility --fresh-resolve  # what a new install would select
mq-agent stack compatibility --strict         # WARN exits 1
mq-agent stack compatibility --all            # whole stack, not just the MCP slice
```

## Example output

```text
MQ Stack Contract Gate

  macos-scripts        READY
  mq-agent             READY
  mq-mcp               READY
  repo-signal          READY
  mq-hal               DRIFT  missing .mq/repo-contract.json
  mq-image-analyze     READY
  mq-ums               READY
  atlas-one            READY

✗ Stack contract: NOT READY
  → mq-hal: missing .mq/repo-contract.json
```

## JSON output

```bash
mq-agent stack contract-check --json
```

```json
{
  "overall": "NOT READY",
  "reasons": ["mq-hal: missing .mq/repo-contract.json"],
  "repos": [
    {"name": "mq-agent", "status": "READY", "reason": ""},
    {"name": "mq-hal",   "status": "DRIFT", "reason": "missing .mq/repo-contract.json"}
  ],
  "checked_at": "2026-06-10T10:00:00+00:00"
}
```

## Typical workflow

When releasing a new version of any MQ repo:

```bash
# 1. Bump VERSION
echo "1.12.0" > VERSION

# 2. Update the contract version to match
jq '.version = "1.12.0"' .mq/repo-contract.json > /tmp/c.json && mv /tmp/c.json .mq/repo-contract.json

# 3. Run the gate
mq-agent stack contract-check
```

## CI mode

In GitHub Actions only the repo under test is checked out — the sibling repos
in `~/` do not exist. Running the gate plainly there would report every sibling
as BLOCKED. The `--ci` flag fixes this:

```bash
mq-agent stack contract-check --ci --json
mq-agent stack release-check --ci --json
```

In CI mode:

* A repo missing from the workspace is reported as **SKIPPED** and never fails the gate.
* The CI checkout itself is detected via its directory name (the checkout
  directory equals the repo name) and is **fully validated** — version sync,
  required fields, README. A DRIFT or BLOCKED in the checked-out repo still
  exits 1.
* The JSON output gains a `mode` field (`"ci"` or `"local"`).

The repo ships `.github/workflows/mq-stack-gate.yml` with two jobs:

* **`pr-gate`** (pull requests) — fast, isolated: runs both gates with `--ci`
  so the PR is judged only on the mq-agent checkout. Unrelated drift in a
  sibling repo cannot fail an mq-agent PR.
* **`full-stack-gate`** (push to `main`, nightly cron, manual dispatch) —
  checks out every MQ stack repo, links them into the expected home layout,
  and runs both gates without `--ci`, validating the whole stack.

```yaml
- name: Stack contract gate
  run: mq-agent stack contract-check --ci --json

- name: Stack release gate
  run: mq-agent stack release-check --ci --json
```

This means a version bump that forgets to update `.mq/repo-contract.json`
fails the PR before it can merge, while stack-wide drift is still caught on
`main` and in the nightly run.

## Companion commands

```bash
mq-agent stack sweep          # score every repo
mq-agent stack report         # score + trend + ready
mq-agent stack release-check  # VERSION/CHANGELOG/branch gate
mq-agent stack release-notes  # commits since last tag
mq-agent stack contract-check # contract manifest gate  ← this command
```
