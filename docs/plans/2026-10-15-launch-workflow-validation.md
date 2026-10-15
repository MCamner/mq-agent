# Launch workflow implementation validation

Date: 2026-10-15. Local implementation; no commit, push, PR creation or deployment.

## Changes

- macos-scripts: canonical target before launcher cwd changes, bounded `do` delegation, shared auth/doctor credential availability.
- mq-mcp: explicit allowlisted target roots for workflow tools, structured root/commit/results, measured review coverage and bounded context.
- mq-agent: deterministic exact task vocabulary, target identity/drift checks, bounded optional context, measured receipt and existing sanitized observation references, explicit recording confirmation.
- mq-hal: deterministic receipt rendering with no session logging or model/router calls.

## Verification observed

- mq-agent broad suite excluding the separately run live receiver module: 2704 passed. Command: `pytest -q --ignore=tests/test_receiver_process_live.py`.
- Live receiver module: 4 passed, 1 pytest import-rewrite warning, using a dedicated test port and scratch PID file. No real API credential was used.
- Final workflow-focused suite: 205 passed; final new regression module: 16 passed.
- Packaging: 4 passed after allowing the build dependency fetch.
- mq-agent mypy: no issues in 19 checked source/test files; scoped Ruff passed.
- Generated command reference check and docs consistency passed.
- mq-mcp target, receipt, server receipt and tool surface group: 42 passed.
- Launcher/doctor focused regressions and relevant registry/routing smoke checks passed; independent launcher review passed.
- HAL receipt smoke, docs smoke and main 28-step smoke passed; independent HAL review passed.
- Independent re-reviews accepted the corrected MCP and mq-agent result handling.
- Diff checks passed in every worktree. Added-line and new mq-agent file scans found no private user paths or token-like values.

The first broad run failed on a then-stale generated command reference and sandbox cache/receiver access. The reference was regenerated, packaging and isolated receiver tests passed separately, and the broad rerun above passed.

## Limits and integration

- Main checkouts and installed services have not been updated. These are local branches for review, not published PRs.
- No live model/API review has been verified. A complete review with unknown verification must remain overall non-PASS.
- Existing diagnostic/release template semantics are preserved; task selection is a small explicit vocabulary rather than general natural-language planning.
- Image-only or unsupported changed files remain incomplete; this implementation does not invent visual-review coverage.
- Review failure detection remains conservative text classification and can reject valid output containing failure terms.
- The existing thread-backed runner cannot forcibly terminate an already running Python call. Producer and transport timeouts remain necessary.
- MCP pytest uses the server Python with a 120-second limit. Tracked HEAD diffs exclude untracked files.
- No learned-routing, approval/promotion policy or shared mqobsidian schema was changed.
