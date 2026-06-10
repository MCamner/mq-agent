# mq-agent Roadmap

mq-agent is a terminal-native workflow orchestration runtime for the mq ecosystem.

It connects safe local execution, repo intelligence, MCP tools, mqlaunch workflows,
and semantic repository memory into one controlled, operator-driven orchestration
surface.

---

## Current status

Current project phase:

```text
v1.12.0 — CI integration for stack gates (done)
Next:    v1.13.0 — mqobsidian stack truth export
```

Completed foundation:

* Terminal-native CLI
* Planner / Executor / Verifier architecture
* Safety modes
* Tool registry
* repo-signal integration (v0.7.0+ with version guard)
* mq-mcp bridge (mq-mcp v1.3.0, 66 tools, safety classes A–D)
* mqlaunch integration (menu + direct commands + demo-flow entry)
* mq-image-analyze perception tool integration
* Command surface documentation
* Semantic repository memory
* GitHub Pages documentation
* Release hygiene and docs consistency checks
* Protected `main` workflow
* Browser-assisted verification workflows (read-only, operator-approved)
* Declarative task runner with `{{step:name}}` templates
* Controlled specialist orchestration
* `run_task` tool — task chaining
* End-to-end demo flow: signal → review → release-check → brain
* mqobsidian second brain integration (brain record-review, brain decide, learn promote)
* Stack contract gate across active MQ repos
* CI-enforced stack gate on PRs and pushes to `main`

---

## Release map

| Version | Theme                                        | Status  |
| ------- | -------------------------------------------- | ------- |
| v0.1.0  | Project foundation                           | Done    |
| v0.2.0  | Repo productization                          | Done    |
| v0.3.0  | Local tool orchestration via mq-mcp          | Done    |
| v0.4.0  | mqlaunch integration                         | Done    |
| v0.4.1  | Consistency, readability and release hygiene | Done    |
| v0.5.0  | Semantic repository memory                   | Done    |
| v0.5.1  | Semantic memory hardening                    | Done    |
| v0.5.2  | mcp start/stop process management            | Done    |
| v0.6.0  | Controlled agent loops (task runner)         | Done    |
| v0.6.1  | Orchestration stabilization                  | Done    |
| v0.7.0  | Browser-assisted verification workflows      | Done    |
| v0.8.0  | Controlled specialist orchestration          | Done    |
| v0.9.0  | Orchestration kernel consolidation           | Done    |
| v1.0.0  | Stable orchestration platform                | Done    |
| v1.1.0  | mq-mcp review runtime integration            | Done    |
| v1.2.0  | mq-mcp semantic memory + risk review routing | Done    |
| v1.3.0  | Architecture memory, model-selection, learn  | Done    |
| v1.4.0  | mq-image-analyze perception tool integration | Done    |
| v1.5.0  | End-to-end demo flow                         | Done    |
| v1.6.0  | Stack-wide health                            | Done    |
| v1.7.0  | Repo health history                          | Done    |
| v1.8.0  | Stack alert                                  | Done    |
| v1.9.0  | Stack report + release gate                  | Done    |
| v1.10.0 | Stack release notes                          | Done    |
| v1.11.0 | Stack contract gate                          | Done    |
| v1.12.0 | CI integration for stack gates               | Done    |
| v1.13.0 | mqobsidian stack truth export                | Next    |

---

## Completed

### v1.12.0 — CI integration for stack gates

* [x] `.github/workflows/mq-stack-gate.yml` — GitHub Actions workflow for stack gates
* [x] Workflow checks out active MQ stack repos into the expected workspace layout
* [x] Workflow links repos to `~/...` paths used by `MQ_STACK_REPOS`
* [x] `mq-agent stack contract-check --json` runs on PRs and pushes to `main`
* [x] `mq-agent stack release-check --json` runs on PRs and pushes to `main`
* [x] CI fails when stack contracts drift or release blockers are detected
* [x] PR #61 verified green before merge

### v1.11.0 — Stack contract gate

* [x] `mq-agent stack contract-check` — validate `.mq/repo-contract.json` across all repos
* [x] `mq-agent stack contract-check --json` — machine-readable; exits 1 on BLOCKED or DRIFT
* [x] Status model: READY → REVIEW (uncommitted) → DRIFT (version mismatch) → BLOCKED (missing)
* [x] `REQUIRED_CONTRACT_FIELDS` frozenset — validates required JSON keys
* [x] `_contract_entry()` helper in `stack_tools.py`
* [x] `schemas/mq_stack_repo_contract.schema.json` — JSON Schema 2020-12
* [x] `.mq/repo-contract.json` seeded in all 7 active stack repos
* [x] `docs/STACK_CONTRACT_GATE.md` — reference with workflow and jq one-liners
* [x] 19 new tests (`test_stack_contract_gate.py`)

### v1.10.0 — Stack release notes

* [x] `mq-agent stack release-notes` — draft notes from git commits since last tag, per repo
* [x] `mq-agent stack release-notes --repo <name>` — single repo filter
* [x] `mq-agent stack release-notes --json` — machine-readable output
* [x] `_release_notes_entry()` helper in `stack_tools.py`
* [x] `docs/STACK_RELEASE_NOTES.md` — reference doc
* [x] 13 new tests (389 total)

### v1.9.0 — Stack report + release gate

* [x] `mq-agent stack report` — score, trend, alert, readiness in one table
* [x] `mq-agent stack report --json`
* [x] `mq-agent stack release-check` — local release gate, exits 1 on blocker
* [x] `mq-agent stack release-check --json` / `--dry-run`
* [x] `docs/STACK_REPORT.md` — reference with workflow
* [x] 15 new tests (376 total)

### v1.8.0 — Stack alert

* [x] `mq-agent stack alert` — exits 1 when a repo dropped ≥ threshold or is below min-score
* [x] `mq-agent stack sweep --alert` — inline alert at end of sweep
* [x] `--threshold N` / `--min-score N` — configurable thresholds
* [x] `--json` — machine-readable, CI-friendly exit codes
* [x] `docs/STACK_ALERT.md` — reference with CI integration examples
* [x] 18 new tests (361 total)

### v1.7.0 — Repo health history

* [x] `stack sweep` appends every non-dry-run run to `~/.mq-agent/sweep-history.jsonl`
* [x] `mq-agent stack history` — tabular trend view, last N sweeps
