# mq-agent Roadmap

mq-agent is a terminal-native workflow orchestration runtime for the mq ecosystem.

It connects safe local execution, repo intelligence, MCP tools, mqlaunch workflows,
and semantic repository memory into one controlled, operator-driven orchestration
surface.

---

## Current status

Current project phase:

```text
v1.20.0 — Autonomous stack (done)
Next:    v1.21.0 — mq-hal operator layer readiness
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
| v1.13.0 | mqobsidian stack truth export                | Done    |
| v1.14.0 | Stack release orchestration                  | Done    |
| v1.15.0 | Brain-integrated stack workflow              | Done    |
| v1.16.0 | Runtime consolidation                        | Done    |
| v1.17.0 | Ollama runtime                               | Done    |
| v1.18.0 | Memory engine                                | Done    |
| v1.19.0 | Operator dashboard                           | Done    |
| v1.20.0 | Autonomous stack                             | Done    |
| v1.21.0 | mq-hal operator layer readiness              | Planned |

---

## Recently Completed

### v1.16.0 — Runtime consolidation

Goal: keep mq-agent focused as the orchestrator while reducing parallel paths.

The runtime boundary remains:

```text
mqlaunch → starts
mq-agent → orchestrates
mq-mcp → runs
repo-signal → measures
mqobsidian → remembers
ollama → reasons
mq-hal → presents
```

* [x] Consolidate overlapping entrypoints by making `mq-agent run --stack`
  the canonical root runtime while keeping `signal`, `review`, `learn`, and
  `truth-export` as focused escape hatches.
* [x] Define one canonical orchestration pipeline in runtime output:
  discover → repo-signal → review → learn → truth-export → release → dashboard.
* [x] Add `mq-agent stack run` as the first stack runtime surface with
  `--dry-run`, `--json`, `--markdown`, `--brain`, `--ci`, and `--approve`;
  expose it from the canonical root surface as `mq-agent run --stack`.
* [x] Add `docs/MQ_CONTROL_PLANE.md` — one system map for signal, review,
  learn, memory and release.

## Completed

### v1.18.0 — Memory engine

Goal: make mqobsidian usable as a local long-term memory engine from mq-agent,
not just a write target for exports.

* [x] `mq-agent memory ingest` — read-only Markdown index across truth,
  reviews, learn, releases, architecture, decisions and stack runs
* [x] `mq-agent memory query` / `memory search-vault` — local vault search
  without mq-mcp or vector-store dependencies
* [x] `mq-agent memory summarize` — section-level note, word and tag summary
* [x] `mq-agent memory link` — read-only link candidates between notes
* [x] `memory_engine.v1` registered in `.mq/repo-contract.json`
* [x] `docs/MEMORY_ENGINE.md`
* [x] Keep write-backed links out of v1.18.0 and defer them to a later
  explicit approval flow

### v1.17.0 — Ollama runtime

Goal: make Ollama a first-class runtime dependency with explicit model
profiles and operator-visible status.

* [x] `mq-agent models` — first-class command group for local model runtime
* [x] `mq-agent models list` — list local Ollama models
* [x] `mq-agent models current` — show active profile and model
* [x] `mq-agent models switch` — switch active profile or assign model to a
  profile, with `--approve` required for writes
* [x] `mq-agent models bench` — local Ollama smoke benchmark
* [x] `~/.mq-agent/models.json` — profile config for `fast`, `review`,
  `planner`, and `memory`
* [x] `mq-agent stack run` — shows active model profile in the Ollama check
* [x] v1.17.0 release docs/status sync
* [x] Full test suite and stack gates before PR

## Planned

### v1.20.0 — Autonomous stack

Goal: move from dashboards to controlled stack loops without allowing
unsupervised writes.

* [x] `mq-agent stack loop` — controlled loop plan from the operator
  dashboard next action
* [x] `mq-agent stack loop --json` — machine-readable plan for
  orchestration
* [x] Non-approved loop execution is blocked until explicit approval is passed
* [x] `mq_stack_loop_plan.v1` schema documents the controlled loop contract
* [x] Command-specific rollback behaviour is documented and tested
* [x] mqlaunch menu entry runs the manual loop plan
* [x] Add approved execution for allowlisted `truth-export` and
  `stack-release` actions

### v1.19.0 — Operator dashboard

Goal: make stack operations visible from one operator surface before moving
toward controlled autonomous loops.

* [x] `mq-agent dashboard` — read-only snapshot for stack health, release
  readiness, mqobsidian truth freshness, Ollama profile status, repos and
  contracts
* [x] `mq-agent dashboard --json` — machine-readable operator state
* [x] `mq-agent tui` — starts with the same operator snapshot before command
  execution
* [x] Add refresh-oriented TUI panels for stack, release, brain and models
* [x] Add operator dashboard reference documentation
* [x] Add dashboard documentation to the GitHub Pages index

### v1.21.0 — mq-hal operator layer readiness

Goal: keep `mq-agent` as the control-plane truth producer and make its
operator-facing outputs stable enough for `mq-hal` to become the daily
operator layer.

`mq-agent` should produce the truth. `mq-hal` should show the truth.
`mqobsidian` should remember the truth.

* [ ] Stable JSON outputs for the surfaces `mq-hal` should read:
  `mq-agent stack cockpit --json`, `mq-agent stack brain-gate --json`,
  `mq-agent run --stack --json`, `mq-agent stack release-check --json`, and
  `mq-agent dashboard --json`
* [ ] Contract tests for the fields needed by `mq-hal stack`,
  `mq-hal brain-status`, `mq-hal release-status`, and `mq-hal next-action`
* [ ] `mq-agent → mq-hal` read-contract documentation, including that `mq-hal`
  must not own gates or write flows
* [ ] Compact `next_action` contract section covering source command,
  severity, suggested route and whether approval is required
* [ ] Defer stack-loop audit history until the `mq-hal` operator layer can
  display current truth cleanly
* [ ] Register `mq_hal_operator_contract.v1` in `.mq/repo-contract.json`

---

### v1.15.0 — Brain-integrated stack workflow

* [x] `mq-agent stack cockpit` — merged stack view: version, branch, dirty, contract, release gate, brain-export freshness, next action per repo
* [x] Flag contract across the command surface: `--dry-run` never writes, `--json` machine-readable, `--brain` respects `--dry-run`, `--approve` required for write flows
* [x] Fixed `signal --brain --dry-run` writing to the brain despite dry-run
* [x] `mq-agent brain structure` — standard mqobsidian export structure (`memory/stack-truth/`, `memory/reviews/`, `memory/learn/`, `mq-stack/runs/`, `mq-stack/roadmaps/`) with `--init --approve` and legacy detection
* [x] `mq-agent stack brain-gate` — pre-release checklist: contract-check + release-check + truth-export dry-run + vault structure + review→brain write path
* [x] `docs/STACK_COCKPIT.md`, `docs/VAULT_STRUCTURE.md`, `docs/BRAIN_GATE.md` — reference docs
* [x] 56 new tests (511 total)

### v1.14.0 — Stack release orchestration

* [x] `mq-agent stack release --repo <name>` — orchestrated single-repo release: release-check pre-gate, version bump, contract sync, changelog from release-notes draft, commit, tag, push
* [x] Dry-run by default; `--execute` applies; abort on first failed step with pre-commit rollback
* [x] Closing `truth-export` after a successful release
* [x] `docs/STACK_RELEASE.md` — reference doc
* [x] 27 new tests (455 total)

### v1.13.0 — mqobsidian stack truth export

* [x] `mq-agent stack truth-export` — durable truth note (contract + release gates) to mqobsidian
* [x] `mq-agent stack export` kept as backwards-compatible alias
* [x] `mq_agent/tools/stack_truth.py` — snapshot builder, Markdown renderer, `stack_truth_export` tool
* [x] Default note path `~/mqobsidian/memory/stack-truth/YYYY-MM-DD-mq-stack-truth.md`
* [x] `--ci` mode for `stack contract-check` / `stack release-check` — SKIPPED for missing repos
* [x] `mq-stack-gate.yml` split into `pr-gate` (--ci on PRs) and `full-stack-gate` (main/nightly/dispatch)
* [x] `docs/STACK_TRUTH_EXPORT.md` — reference doc
* [x] 25 new tests (439 total)

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
