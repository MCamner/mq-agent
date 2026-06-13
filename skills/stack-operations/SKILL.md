---
name: stack-operations
description: Use when working on mq-agent stack commands — sweep, report, alert, history, cockpit, release-check, release-notes, contract-check, release, loop, brain-gate, truth-export — or the .mq/repo-contract.json stack contract.
---

# Stack Operations

Own mq-agent's cross-repo stack suite: the commands that observe, gate, remember, and act on the MQ stack.

## When to use

- Adding or changing any `mq-agent stack <command>` behavior
- Changing the contract gate, `.mq/repo-contract.json` schema, or gate statuses (READY/DRIFT/BLOCKED)
- Changing sweep scoring, alert thresholds, history storage, or cockpit panels
- Changing the orchestrated release pipeline (`stack release`) or release-notes drafting
- Debugging why a stack gate passes or fails

## When not to use

- Single-repo release validation — use `release-readiness`
- Routing review cognition through mq-mcp — use `mq-mcp-review-orchestration`
- Single-repo audit or signal scoring — use `repo-audit` / `signal-assessment`
- mqlaunch menu routing to stack commands — macos-scripts' `mqlaunch-command-surface`

## Evals

### Should trigger

- "stack sweep gives mq-hal the wrong score"
- "add a new check to the contract gate"
- "stack release should also update the cockpit state"
- "why does stack alert not fire on the score drop?"

### Should not trigger

- "is mq-agent itself ready to release?" → use `release-readiness`
- "route security review through mq-mcp" → use `mq-mcp-review-orchestration`
- "audit this single repo" → use `repo-audit`
- "add the sweep to the mqlaunch menu" → macos-scripts' `mqlaunch-command-surface`

## Command surface

The suite observes, gates, remembers, and acts:

| Stage | Commands |
| ----- | -------- |
| Observe | `stack status`, `stack report`, `stack sweep`, `stack history`, `stack cockpit` |
| Gate | `stack alert`, `stack release-check`, `stack contract-check`, `stack skills-check`, `stack brain-gate` |
| Remember | `stack truth-export` (alias `export`) |
| Act | `stack release-notes`, `stack release`, `stack run`, `stack loop` |

All gates support `--json` and exit 1 on failure so CI and mqlaunch can consume them.

`stack skills-check` runs each repo's `scripts/check-skills.sh` and is the
cross-repo enforcement for skill consistency (dead cross-references, frontmatter
gaps, path drift, SKILLS.md sync). A repo with a `skills/` directory but no
validator is reported as REVIEW, not a failure — that is the nudge to add
`check-skills.sh` to that repo.

## Core files

- `mq_agent/main.py` — `stack_app` command definitions
- `mq_agent/tools/stack_tools.py`
- `mq_agent/tools/stack_release.py`
- `mq_agent/tools/stack_loop.py`
- `mq_agent/tools/brain_gate.py`
- `.mq/repo-contract.json` — this repo's own contract manifest
- `docs/STACK_HEALTH.md`, `docs/STACK_CONTRACT_GATE.md`, `docs/STACK_RELEASE.md`, `docs/STACK_ALERT.md`, `docs/STACK_REPORT.md`, `docs/STACK_RELEASE_NOTES.md`, `docs/STACK_COCKPIT.md`, `docs/STACK_HISTORY.md`, `docs/STACK_LOOP.md`, `docs/STACK_TRUTH_EXPORT.md`, `docs/BRAIN_GATE.md`
- `tests/test_stack_*.py` — one test module per stack surface

## Contract gate rules

- Every MQ repo (except mqobsidian) must have `.mq/repo-contract.json` with `repo`, `role`, `version`, `status`, and `contracts`.
- `version` in the contract must match the repo's `VERSION` file — bumping one without the other produces DRIFT.
- Missing repo or missing `VERSION` is BLOCKED; gate exits 1 on any BLOCKED or DRIFT.
- New stack capabilities get a versioned contract id (e.g. `stack_sweep.v1`) appended to the `contracts` list.

## Change rules

1. Keep JSON output shapes stable and schema-tagged — downstream consumers (mqlaunch, CI, HAL) parse them.
2. Gates must exit 1 on failure; never report READY on partial data.
3. Dry-run is the default for `stack release`; `--execute` is the explicit opt-in.
4. Update the matching `docs/STACK_*.md` and the contract id list when behavior changes.
5. Add or extend the matching `tests/test_stack_*.py` module — every stack surface has one.
6. Stack logic lives here; mqlaunch only routes to it, mq-mcp only provides cognition.

## Verification

```bash
python -m pytest tests/test_stack_contract_gate.py -q   # focused
python -m pytest -k stack -q                             # whole suite
mq-agent stack contract-check
mq-agent stack sweep --dry-run
./release-check.sh
```

## Report format

For gate work, state: gate name, repos checked, statuses with reasons, exact command that proved it, and whether JSON consumers are affected.
