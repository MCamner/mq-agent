# Verify changed files

`mq-agent verify-changes` selects repository-owned checks for staged, unstaged,
deleted, renamed and untracked non-ignored files. `mqlaunch verify-changes` is
its terminal entrypoint and forwards the caller's directory to mq-agent.

```bash
mqlaunch verify-changes --plan
mqlaunch verify-changes
mqlaunch verify-changes --check-receipt
mqlaunch verify-changes --base origin/main --json
mq-agent verify-changes /path/to/repo --base HEAD~1 --plan
```

The default base is `HEAD`: only uncommitted changes are selected. For committed
changes, explicitly choose a base such as `HEAD~1` or `origin/main`. The base is
a direct Git comparison, not a merge-base/three-dot comparison. No fetch runs.
`--repo PATH` overrides the positional repository argument. Run only in trusted
local repositories: their configured tests execute repository code.

## Repository rules

Each repository owns `.mq/verification.json`. Example:

```json
{
  "schema": "mq.verification-config.v1",
  "checks": [
    {
      "id": "doctor-auth",
      "runner": "bash",
      "targets": ["tests/doctor-auth-smoke.sh"],
      "paths": ["tools/scripts/doctor.sh", "tools/scripts/auth.sh", "tests/doctor-*.sh"],
      "timeout_seconds": 120
    }
  ]
}
```

Patterns use Python `fnmatchcase` on repo-relative paths; `*` also matches `/`.
Every matching check runs once, in configured order. No checks are inferred from
file names, CodeGraph or a model. Unmatched files are listed explicitly.

Supported runners:

| Runner | Execution |
| --- | --- |
| `bash` | One repo-local shell script |
| `bash-syntax` | Syntax check of one repo-local shell script |
| `python` | One repo-local Python script |
| `pytest` | Explicit repo-local test files/directories |

Commands are built as argument lists with no shell evaluation. Inline commands,
custom executables, option injection and targets escaping the repo are refused.
Each timeout is an integer from 1 to 900 seconds. At most 64 checks are allowed.
Targets must exist before any selected check starts. A missing tool or nonzero
exit fails the check; a timeout terminates its process group. Stdin is closed.
Tests can create their usual temporary/generated files; this is not a sandbox.

Python checks use the interpreter running mq-agent. A nested Python project may
set `"python_project": "mq-mcp"` at the config root; execution then uses
`uv --directory mq-mcp run --no-sync python`. Dependencies must already be
installed. Verification does not install dependencies or start model services.

## Receipts and exit codes

A run writes one local receipt at the worktree-specific Git path returned by
`git rev-parse --git-path mq-verification/receipt.json`. It replaces that
worktree's previous receipt atomically. `--plan` and `--check-receipt` do not
write or run checks. They cannot be combined.

The receipt records commit, resolved base, file/index fingerprint, selected
checks, exit codes, durations, uncovered files and completion time. The
fingerprint covers **all tracked and non-ignored untracked files**, not only
selected files, plus the config and verifier implementation. Tests editing
those files during execution make the run `STALE`. Staging, changing the base
or editing a test also invalidates an earlier receipt. Ignored files and
external dependency contents are outside its scope. External symlinks are
recorded as links, without reading their target contents.

Child stdout/stderr are deliberately discarded: receipts contain no test logs
or credential values. For a failed check, use its runner and targets from the
plan/config to rerun it directly and inspect the diagnostic output.

| Status | Meaning | Exit |
| --- | --- | --- |
| `PASS` | Every changed file matched and every selected check passed | 0 |
| `PLAN` | Preview only; inspect uncovered files before running | 0 |
| `NO_CHANGES` | Nothing differs from the selected base; no checks ran | 0 |
| `FAIL` | At least one selected check failed, timed out or could not start | 1 |
| `INCOMPLETE` | Some changed files have no matching rule | 1 |
| `STALE` | The source/index/base/verifier differs from the receipt | 1 |
| `MISSING` | No previous receipt for this worktree | 1 |
| `ERROR` | Invalid configuration, receipt or Git invocation | 2 |

`--json` prints exactly one JSON document, without child output or progress.
Receipts use `mq.verification-receipt.v1` and include a checksum for accidental
corruption detection. They are editable local evidence, **not signed
attestations, approval, CI results or permission to publish**. A successful exit
from configured tests does not prove test quality, API key validity, runtime
service health, external dependency freshness or full release readiness.

## Initial coverage

- macos-scripts: doctor/auth regression checks, terminal delegation and command
  registry/stack boundaries.
- mq-mcp: Learn extraction and context contracts; nested Python environment.
- mq-agent: verification regression tests and documentation consistency.

These are deliberately bounded rule sets. Unrelated edits produce
`INCOMPLETE`; add reviewed rules rather than a catch-all that hides gaps.
Review and release provider selection is unchanged: this command calls no LLM.
