# mqlaunch Workflow Automation Implementation Plan

## Goal

Bind bounded workflows to the intended repository, select approved templates from explicit tasks, and report measured execution receipts consistently.

## Owner repo

mq-agent

## Secondary repos

macos-scripts, mq-mcp, mq-hal. mqobsidian is a read-only contract reference unless an existing observation contract cannot represent the needed references.

## Architecture boundary

- mq-agent owns deterministic task selection, context acquisition, execution and the local workflow receipt.
- macos-scripts owns argument forwarding and credential/doctor presentation.
- mq-mcp owns target-aware tools and truthful structured results.
- mq-hal renders mq-agent's receipt without recomputing verdicts.
- mqobsidian owns durable shared observation contracts; preserve those contracts unchanged.
- repo-signal owns repository quality signals; invoke existing interfaces only.

## Non-goals

No free shell planning, learned routing, activation, promotion, service lifecycle changes, or automatic commits/pushes/releases.

## Approval gates

- Before file writes: already authorized by the request to implement PR 1–3.
- Before commit: requires a separate explicit request.
- Before push/merge: requires a separate explicit request.
- Before deletion/settings changes: requires separate approval.

## Test gates

- mq-agent: uv run pytest -q tests/test_workflow*.py
- macos-scripts: focused launcher, doctor/auth and registry tests discovered in tests/; shell syntax checks.
- mq-mcp: focused target binding and tool-result tests plus tool-surface drift checks when applicable.
- mq-hal: uv run pytest -q for receipt/CLI tests and existing suite as feasible.
- Final: git diff --check in every worktree; inspect changed public output for secrets/private paths.

## Rollback

Uncommitted isolated branches leave installed runtimes and main checkouts unchanged. After authorized integration, revert each logical change in reverse consumer-to-producer order. Never delete existing worktrees or user changes.

### Task 1: Reliable launch and target binding (PR 1)

**Files:** macos-scripts terminal/menus/mq-agent-menu.sh, tools/scripts/doctor.sh and existing auth resolver; mq-agent mq_agent/workflows/{runner,state,cli}.py and new target helper; mq-mcp tool implementations for git_diff, review_diff, run_tests and focused tests.
**Steps:** reproduce wrong-target behavior with repo A/server B fixtures; normalize paths before launcher cwd changes; bind canonical root/commit in run state; map only supported arguments; reject mismatched target; use auth resolver in doctor; show service requirements by selected workflow.
**Expected result:** all repo-bound steps execute against A despite server B, invalid targets fail closed, Keychain availability avoids false missing-env warnings; unrelated services do not block fixed workflows.
**Commit suggestion:** fix(workflow): bind tools and startup checks to the requested target

### Task 2: Bounded deterministic task entry (PR 2)

**Files:** mq-agent mq_agent/workflows/{cli,templates,policy}.py, new selection/context helper, existing main CLI registration and tests; macos-scripts launcher dispatcher/registry/help/tests.
**Steps:** add mqlaunch do forwarding to mq-agent; explicit allowlisted Swedish/English intent mapping to approved review, diagnostics/preflight and release templates; unknown/ambiguous requests fail without executing; show selection reasons and actual context sources; bounded local context cards, CodeGraph only when needed, repo-signal through existing tool; retain runner policy and approval gates.
**Expected result:** same clear request yields same plan; absent services, unknown intent and interrupted runs are tested; no raw task text is copied into memory.
**Commit suggestion:** feat(workflow): select approved workflows from explicit tasks

### Task 3: Shared measured receipt (PR 3)

**Files:** mq-agent mq_agent/workflows/{state,runner,storage,cli,observation}.py and new receipt module; mq-hal CLI/receipt renderer and tests; docs for new commands and side effects.
**Steps:** reuse existing workflow run state and workflow-observation.v1; receipt is mq-agent-owned command output, not a new shared memory schema. Include run/observed execution ids, root/commit/runtime, planned/terminal steps, coverage separate from verification, actual tools/fallback, storage confirmation, next action and approval need. Preserve unknown metrics. Never fabricate execution links. Emit sanitized existing observation with references; expose emission failures. HAL accepts receipt JSON and presents the same verdict. Resume must preserve completed steps and target identity.
**Expected result:** partial/interrupted/limited results cannot become overall PASS; unknown remains null/unknown; failed storage is visible; CLI/HAL/observation agree on completed versus remaining steps; resume does not duplicate completed work.
**Commit suggestion:** feat(workflow): report measured receipts across CLI and HAL

## Execution and review

Implement in isolated worktrees with focused regression tests first. Use separate implementer/spec/quality review roles per mq-subagent-driven-development. Verify owner boundaries before extending any contract; no unmerged canonical schema vendoring. Document any remaining gap rather than claiming acceptance.
