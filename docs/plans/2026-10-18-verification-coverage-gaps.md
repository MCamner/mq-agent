# Verification Coverage Gaps Implementation Plan

## Goal

Reject broken rules early, verify mq-mcp README consistency and report runtime data honestly.

## Owner repo

mq-agent

## Secondary repos

mq-mcp

## Architecture boundary

mq-agent owns selection, execution and receipts. mq-mcp owns its rules and docs checks.
macos-scripts remains a thin unchanged delegate. mqobsidian owns durable memory;
repo-signal owns repository health, and mq-hal owns operator summaries.

## Non-goals

No history rewriting, automatic acknowledgement of runtime data or provider changes.

## Approval gates

- Before file writes: no; user requested implementation.
- Before commit: yes.
- Before push/merge: yes.
- Before deletion/settings changes: yes.

## Test gates

- mq-agent: `.venv/bin/python -m pytest tests/test_verify_changes.py tests/test_command_reference.py -q`
- mq-mcp: `mq-mcp/.venv/bin/python -m pytest tests/test_verification_config.py -q`
- Both: `mqlaunch verify-changes --plan` and `mqlaunch verify-changes --json`

## Rollback

Restore only the feature changes in the verifier, its tests/docs and mq-mcp rules.
Preserve pre-existing runtime history byte-for-byte.

### Task 1: fail-fast validation and runtime classification

Modify mq_agent/verify_changes.py, mq_agent/main.py and tests/test_verify_changes.py.
Prove missing unselected targets fail and pending runtime data never counts as verified code.

### Task 2: reuse real README checks

Modify mq-mcp .mq/verification.json and README.md; add tests/test_verification_config.py.
Prove positive controls and deliberate README version/tool-reference failures.

### Task 3: documentation and final checks

Update docs/VERIFY_CHANGES.md, run focused tests and real CLI checks, compare history hash.
