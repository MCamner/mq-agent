# Verify Changes Implementation Plan

## Goal

Select explicit repo checks for changed files and issue stale-detecting local evidence.

## Owner repo

mq-agent

## Secondary repos

macos-scripts, mq-mcp

## Architecture boundary

mq-agent owns orchestration and receipts. macos-scripts delegates. Each repo owns its check rules.
mq-mcp remains the review/execution-tool owner; no review provider changes.
mqobsidian owns durable memory; repo-signal owns repo health.

## Non-goals

No automatic commits, push, merge, model-generated commands, or release approval.

## Approval gates

- Before file writes: no; user explicitly requested implementation.
- Before commit: yes.
- Before push/merge: yes.
- Before deletion/settings changes: yes.

## Test gates

- mq-agent: `.venv/bin/python -m pytest tests/test_verify_changes.py -q`
- mq-agent: `.venv/bin/python tools/generate_command_reference.py --check`
- macos-scripts: `bash tests/verify-changes-smoke.sh`
- macos-scripts: `python3 tools/scripts/validate-command-registry.py`
- macos-scripts: `bash tests/mq-stack-contract-smoke.sh`
- mq-mcp: `uv --directory mq-mcp run --no-sync pytest ../tests/test_learn_engine.py -q`

## Rollback

Remove only the new verification module, configs, tests and documentation; restore the added CLI routes.
Preserve all pre-existing changes and local evidence.

### Task 1: selection, execution and receipts

Files: mq_agent/verify_changes.py, mq_agent/main.py, tests/test_verify_changes.py.
Prove staged/untracked/deleted selection, failures, timeout, uncovered files and stale receipts.

### Task 2: terminal integration and repo rules

Files: terminal/launchers/mqlaunch-command-mode.sh, mqlaunch/lib/command-registry.json,
tests/verify-changes-smoke.sh and .mq/verification.json in the three repos.
Prove forwarding of caller directory, arguments and delegate exit status.

### Task 3: documentation and review

Files: docs/VERIFY_CHANGES.md, README.md, docs/COMMANDS.md, generated command reference.
Run focused tests, syntax/lint and real plan/run checks. Summarize remaining limits.
