# mq-agent Roadmap

mq-agent is a terminal-native workflow orchestration runtime for the mq ecosystem.

It connects safe local execution, repo intelligence, MCP tools, mqlaunch workflows,
and semantic repository memory into one controlled, operator-driven orchestration
surface.

---

## Current status

Current project phase:

```text
Released: v1.25.1 — Release Cockpit post-release audit fix
Current:  v1.26.0 — Stack Compatibility Gate
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
| v1.21.0 | mq-hal operator layer readiness              | Done    |
| v1.22.0 | Inbox ranking and promotion orchestration    | Done    |
| v1.23.0 | Cross-repo release automation                | Done    |
| v1.24.0 | PR-mediated release flow                     | Done    |
| v1.24.1 | Post-release stabilization                   | Done    |
| v1.25.0 | Release Cockpit                              | Released |
| v1.25.1 | Release Cockpit post-release audit fix       | Released |
| v1.26.0 | Stack Compatibility Gate                     | In progress |

---

## Next release

### v1.26.0 — Stack Compatibility Gate

Goal: detect dependency and machine-readable contract incompatibilities across
MQ repositories before installation, release, or runtime. The command remains
read-only and reports unavailable evidence explicitly rather than guessing.

Planned operator surface:

```bash
mq-agent stack compatibility
mq-agent stack compatibility --json
mq-agent stack compatibility --fresh-resolve
```

Delivery order:

1. Define `mq.stack-compatibility.v1`, status semantics, evidence, blocker
   codes, and negative contract tests.
2. Add network-free repository inventory for declared and locked dependencies,
   starting with `mq-mcp` and `mq-image-analyze`.
3. Compare dependency ranges plus produced and consumed MQ contracts.
4. Add explicit `--fresh-resolve` using temporary environments without
   modifying repositories or lockfiles.
5. Integrate human/JSON output, dashboard, CI shadow mode, `mq-hal`, and
   `mqlaunch` without duplicating policy.
6. Expand incrementally across the remaining MQ repositories.

`mq-agent` owns aggregation and assessment. Each repository owns dependency
declarations and compatibility metadata. `mq-hal` may present results and
`mqlaunch` may delegate, but neither owns compatibility logic. The detailed
phase plan and regression case remain canonical in the root `ROADMAP.md`.

## Deferred work

* Optional `ship prepare`, `ship finalize`, and `ship publish` wrappers remain
  deferred until operator evidence shows they improve safety without hiding
  the existing `stack release` proof and approval policy.
* Inbox ingestion of `repo-signal` readiness and `mq-mcp` reviews remains
  blocked on producer-owned, candidate-bearing bounded JSON with explicit
  `producer` and `schema_id`.

## Recently Completed

### v1.25.0–v1.25.1 — Release Cockpit

Released 2026-08-10. v1.24.1 proved the PR-mediated release chain end to end;
v1.25.0 turned the existing release engine into a guided operator experience:
show the current state, explain blockers, recommend one safe next action, and
provide coherent
release proof. v1.25.1 fixed post-release audit classification and completed
the milestone with an `AUDITED` release snapshot.

#### Operator surface

* [x] Add read-only `mq-agent ship status` with human-readable and `--json`
  output.
* [x] Show repository, current and target versions, latest tag and tag target,
  local `main`, CI, release-check, contract-check, stack preflight, release PR,
  and GitHub Release state.
* [x] Add `mq-agent ship proof` for release PR, mergecommit, annotated tag,
  GitHub Release, CI, gate, and local-tree evidence.
* [x] Add `mq-agent ship audit` for a non-mutating post-release verification.

#### State and guidance

* [x] Define and test `IDLE`, `BLOCKED`, `PREFLIGHT_READY`, `PREPARED_PR`,
  `PR_GREEN`, `MERGED`, `FINALIZED`, `PUBLISHED`, and `AUDITED`.
* [x] Define explicit state precedence and require a target version for
  `PREFLIGHT_READY`.
* [x] Treat `AUDITED` as the result of the current verification snapshot.
* [x] Recommend exactly one next action for every state.
* [x] Explain dirty and missing repos, failed CI and gates, blocked preflight,
  existing tags, release-PR state, wrong tag targets, and missing GitHub
  Releases in plain language without hiding the underlying evidence.

#### Architecture and safety

* [x] Keep `stack release` as the lower-level engine.
* [x] Reuse existing planning, gate, preflight, prepare, and finalize
  primitives; do not duplicate release policy.
* [x] Keep the first `ship` scope read-only.
* [x] Keep review, merge, finalize, and publication explicit.
* [x] Do not add a new release mechanism, automatic merge, automatic finalize,
  or unrelated cleanup.

#### Delivery order

1. State model, `ship status`, and JSON contract.
2. Blocker explanations and deterministic next action.
3. `ship proof` and `ship audit`.
4. Command reference, release-cockpit guide, README, and Pages links.

Definition of done: the state contract and blocker mapping are tested,
existing `stack release` behavior remains unchanged, documentation clearly
separates the operator surface from the engine, and main CI plus all release
gates pass without blockers.

---

### v1.24.1 — Post-release stabilization

Released 2026-07-24. The full PR-mediated path was verified through prepare,
green CI, human-controlled merge, explicit finalize, annotated tag targeting
the mergecommit, GitHub Release publication, and post-release audit.

### v1.24.0 — PR-mediated release flow

Released 2026-07-23. Branch-protected repos now prepare a release branch and
draft PR, wait for review and merge, and require explicit finalization before
the merged commit is tagged. Post-release stabilization aligns single-repo
plans with that mode policy, includes `mqobsidian` in contract-check coverage,
and synchronizes operator documentation.

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
* [x] `mq-agent models doctor` — read-only runtime, profile, Modelfile, and JSON diagnostics
* [x] `mq-agent models switch` — switch active profile or assign model to a
  profile, with `--approve` required for writes
* [x] `mq-agent models bench` — measurable Ollama API benchmark with timing,
  token throughput, structured-output validation, and explicit keep-alive
* [x] `~/.mq-agent/models.json` — profile config for `fast`, `review`,
  `planner`, and `memory`
* [x] `mq-agent stack run` — shows active model profile in the Ollama check
* [x] v1.17.0 release docs/status sync
* [x] Full test suite and stack gates before PR

## Completed release details

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

* [x] Stable JSON outputs for the surfaces `mq-hal` should read:
  `mq-agent stack cockpit --json`, `mq-agent stack brain-gate --json`,
  `mq-agent run --stack --json`, `mq-agent stack release-check --json`, and
  `mq-agent dashboard --json`
* [x] Contract tests for the fields needed by `mq-hal stack`,
  `mq-hal brain-status`, `mq-hal release-status`, and `mq-hal next-action`
* [x] `mq-agent → mq-hal` read-contract documentation, including that `mq-hal`
  must not own gates or write flows
* [x] Compact `next_action` contract section covering source command,
  severity, suggested route and whether approval is required
* [x] Stack-loop audit history displayed read-only by the `mq-hal` operator
  layer
* [x] Register `mq_hal_operator_contract.v1` in `.mq/repo-contract.json`

### v1.22.0 — Inbox ranking and promotion orchestration

Goal: make `mq-agent` the owned execution layer for inbox analysis, ranking,
and review-gated promotion, reading truth from `mqobsidian` exports and never
taking over truth ownership or shell runtime.

`mq-agent` runs the workflow. `mqobsidian` owns the schema and remembers the
result. `mqlaunch` stays a thin delegate surface.

* [x] Add `mq-agent obsidian inbox list` / `inbox read` over canonical
  `mqobsidian` inbox exports (read-only).
* [x] Add `mq-agent obsidian inbox rank`: score candidates against the
  canonical ranking fields, merging evidence across sources.
* [x] Add a review-needed vs auto-promotable classification flow using the
  `mqobsidian` promotion-state model.
* [x] Add `mq-agent obsidian promote --dry-run` and `--confirm`, plus
  `reject/defer` and `rollback/deprecate` flows.
* [x] Require traceable source evidence before any promotion; keep mutation
  paths explicit and review-gated.
* [x] Validate expected `mqobsidian` manifests/views before workflow
  execution; fail safely on stale, missing, or drifted truth surfaces.
* Deferred upstream evidence ingestion is tracked under **Deferred work**;
  v1.22 shipped without taking ownership of producer contracts.
* [x] Expose a stable, machine-readable CLI/API surface for `mqlaunch` to
  delegate to; keep ranking and promotion logic out of shell.
* [x] Register `inbox_promotion_orchestration.v1` in the repo contract.

---

### v1.23.0 — Cross-repo release automation

Goal: make the correct release path the only path across repos, without
rebuilding automation that already ships.

Single-repo release automation ships as `stack release`
(`plan_stack_release` / `execute_stack_release`): gate → bump → sync-contract →
changelog → tag → push → truth-export. The full scope, evidence, and the three
botched off-main tags this reframe came from are recorded in the top-level
`ROADMAP.md` scoping note (2026-07-17).

* [x] Converge release paths around contract-safe `stack release` behavior and
  the shared `repo_release_check.v1` preflight contract.
* [x] Add read-only multi-repo preflight plus approval-gated execution in
  dependency order, with fail-fast behavior before mutation.
* [x] Enforce clean, on-main release execution and reject target versions whose
  tag already exists locally or on `origin`.
* [x] Keep the known-bad drifted tags for provenance and fix forward without
  tag deletion, force-push, or history rewriting.

Released as `v1.23.0` on 2026-07-19. GitHub Release metadata was synchronized
after publication so the tag, changelog, package version, README, and Latest
Release surface all identify `v1.23.0` consistently.

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
