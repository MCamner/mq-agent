# mq-agent Roadmap

v1.21.0 — mq-hal operator layer readiness. Done.
Next: v1.23.0 — Cross-repo release automation.

## Current status

All phases complete through v1.21.0.

| Version | Theme | Status |
| --- | --- | --- |
| v1.8.0 | Stack alert | Done |
| v1.9.0 | Stack report + release gate | Done |
| v1.10.0 | Stack release notes | Done |
| v1.11.0 | Stack contract gate | Done |
| v1.12.0 | CI integration for stack gates | Done |
| v1.13.0 | mqobsidian stack truth export | Done |
| v1.14.0 | Stack release orchestration | Done |
| v1.15.0 | Brain-integrated stack workflow | Done |
| v1.16.0 | Runtime consolidation | Done |
| v1.17.0 | Ollama runtime | Done |
| v1.18.0 | Memory engine | Done |
| v1.19.0 | Operator dashboard | Done |
| v1.20.0 | Autonomous stack | Done |
| v1.21.0 | mq-hal operator layer readiness | Done |
| v1.22.0 | Inbox ranking and promotion orchestration | Done |
| v1.23.0 | Cross-repo release automation | Planned |

## v1.16.0 — Runtime consolidation

Goal: keep mq-agent focused as the orchestrator while reducing parallel paths.

The rule remains:

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

## v1.17.0 — Ollama runtime

Goal: make Ollama a first-class runtime dependency with explicit model
profiles instead of incidental learn-backend support.

* [x] Add `mq-agent models` command group.
* [x] Add `mq-agent models list` for local Ollama inventory.
* [x] Add `mq-agent models current` for active profile/model visibility.
* [x] Add `mq-agent models switch` with explicit `--approve` for writes to
  `~/.mq-agent/models.json`.
* [x] Add `mq-agent models bench` for a small local model smoke test.
* [x] Surface active model profile in `mq-agent stack run` Ollama checks.
* [x] Add release docs/status sync for v1.17.0.
* [x] Run full suite and release gates before PR.

Default profiles:

```text
fast
review
planner
memory
```

## Planned after v1.17.0

## v1.18.0 — Memory engine

Goal: make mqobsidian usable as a local long-term memory engine from mq-agent,
not just a write target for exports.

* [x] Add `mq-agent memory ingest` for a read-only Markdown index across
  truth, reviews, learn, releases, architecture, decisions and stack runs.
* [x] Add `mq-agent memory query` / `memory search-vault` for local vault
  search without requiring mq-mcp or a vector store.
* [x] Add `mq-agent memory summarize` for section-level note, word and tag
  summaries.
* [x] Add `mq-agent memory link` for read-only link candidates between notes.
* [x] Register `memory_engine.v1` in the repo contract.
* [x] Add `docs/MEMORY_ENGINE.md`.
* [x] Keep write-backed links out of v1.18.0 and defer them to a later
  explicit approval flow.

## Planned after v1.18.0

* [x] v1.19.0 — Operator dashboard foundation: `mq-agent dashboard`
  read-only snapshot for stack health, release, brain, Ollama, repos and
  contracts.
* [x] TUI startup now shows the operator snapshot before command execution.
* [x] Add refresh-oriented TUI panels for stack, release, brain and models.
* [x] Add operator dashboard reference documentation.
* [x] Add dashboard documentation to the GitHub Pages index.
* [x] v1.20.0 — Autonomous stack foundation: `mq-agent stack loop`
  controlled planning and approved one-step execution.
* [x] Add explicit loop contract schema and rollback behaviour documentation.
* [x] Add mqlaunch menu entry for manual `mq-agent stack loop` planning.
* [x] Add approved execution after command-specific rollback behaviour is
  implemented and tested.

## v1.21.0 — mq-hal operator layer readiness

Goal: keep `mq-agent` as the control-plane truth producer and make its
operator-facing outputs stable enough for `mq-hal` to become the daily
operator layer.

`mq-agent` should produce the truth. `mq-hal` should show the truth.
`mqobsidian` should remember the truth.

* [x] Lock stable JSON outputs for the surfaces `mq-hal` should read:
  `mq-agent stack cockpit --json`, `mq-agent stack brain-gate --json`,
  `mq-agent run --stack --json`, `mq-agent stack release-check --json`, and
  `mq-agent dashboard --json`.
* [x] Add or update contract tests for the fields needed by `mq-hal stack`,
  `mq-hal brain-status`, `mq-hal release-status`, and `mq-hal next-action`.
* [x] Document the `mq-agent → mq-hal` read contract, including that `mq-hal`
  must not own gates or write flows.
* [x] Add a compact `next_action` contract section covering source command,
  severity, suggested route and whether approval is required.
* [x] Add stack-loop audit history now that the `mq-hal` operator layer can
  display approved execution attempts cleanly.
* [x] Register `mq_hal_operator_contract.v1` in the repo contract.

## v1.22.0 — Inbox ranking and promotion orchestration

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
* [ ] **Blocked** — accept `repo-signal` readiness and `mq-mcp` review outputs
  as evidence inputs without moving truth ownership out of `mqobsidian`.
  Blocked by producer contracts (mqobsidian DEC-004): `mq-mcp review_file` emits
  prose, not JSON; `repo-signal` declares `readiness_score.v1` /
  `publish_checklist.v1` but emits neither; and no repo-signal output carries a
  candidate key. Unblocks when a producer emits candidate-bearing, bounded JSON
  evidence with an explicit `producer` and `schema_id`.
* [x] Expose a stable, machine-readable CLI/API surface for `mqlaunch` to
  delegate to; keep ranking and promotion logic out of shell.
* [x] Register `inbox_promotion_orchestration.v1` in the repo contract.

## v1.23.0 — Cross-repo release automation

Goal: automate the MQ release workflow across repos while preserving repo
ownership boundaries, branch protection, and review gates.

Release automation should coordinate:

* `mq-agent` as the orchestration and contract authority
* `repo-signal` for readiness and release gate scoring
* `mqobsidian` for durable truth and release manifest exports
* `mq-mcp` for local test/review orchestration and machine-readable output
* `mq-hal` for operator visibility and next-action guidance

### v1.23.0 checklist

* [ ] Add `mq-agent release plan` to generate a repo-aware release plan from
  current `CHANGELOG.md`, `VERSION`, and `repo-signal` readiness output.
  * This plan should list repos, next version, blockers, and proposed branch
    or PR flow.
* [ ] Add `mq-agent release prepare --repo <name>` for single-repo release
  preparation.
  * Validate `CHANGELOG.md` contains the planned version.
  * Validate `README.md` version badge matches `VERSION`.
  * Validate `repo-signal` readiness and `mq-mcp` review pass status.
  * Update `VERSION`, README badge, and release section in one atomic step.
* [ ] Add `mq-agent release execute --repo <name>` to commit, tag, and push.
  * For non-protected repos, push directly to the release branch.
  * For protected repos, create a `chore/release-v<version>` branch and push
    the changes there.
  * Optionally support `--create-pr` to open the branch as a PR.
* [ ] Add `mq-agent release sync` to align branch protection requirements with
  actual repo rule state.
  * Detect repos needing PR-based flow vs direct push.
  * Use protected repo workflow rules to choose whether to open a PR.
* [ ] Add `mq-agent release gate --json` as a machine-readable release gate
  step for CI and `mq-hal`.
  * Output should include `repository`, `version`, `blocked`, `blockers`, and
    `evidence`.
* [ ] Add `mq-agent release-check --codegraph` to automatically validate
  release workflow impact when `.codegraph/` is available.
  * Auto-query callers/impact for `mq-agent stack release-check`, `stack
    release`, and release-related release orchestration files.
  * Include `codegraph_applied`, `codegraph_queries`, and `codegraph_findings`
    in JSON output.
* [ ] Add `repo-signal readiness --format json` compatibility for release
  automation.
* [ ] Add `mqobsidian release manifest` export for each planned release.
  * Include repo version, changelog heading, branch/PR target, and gate status.
* [ ] Add `mq-hal release-status` and `mq-hal next-action` to show pending
  releases and which repos need PR creation, review, or merge.
* [ ] Add a `docs/STACK_RELEASE.md` update section describing the new cross-repo
  release workflow and PR gating behavior.

### Why this is the next big automation

1. Release automation is the highest-leverage workflow because it spans all
   repos and is currently the biggest source of manual coordination.
2. It preserves the existing architecture: `mq-agent` remains the orchestrator,
   `mqobsidian` remains the durable memory, `repo-signal` remains the gate,
   `mq-mcp` remains the runtime/assertion engine, and `mq-hal` remains the
   operator UI.
3. It reduces human error by turning `Unreleased`/version mismatch/changelog
   drift into deterministic validation and release branch creation.
4. It gives the operator layer an observable workflow rather than a hidden,
   manual sequence of commits and tags.

### Success criteria

* `mq-agent release plan` shows all repos and planned next versions.
* `mq-agent release prepare --repo <name>` passes only if the repo is ready.
* `mq-agent release execute --repo <name>` either pushes a release branch or
  opens a PR when required.
* `mq-hal release-status` shows a coherent release pipeline state for all
  MQ repos.
* Protected repos no longer require manual branch selection for release.
* Release notes and truth exports are generated consistently after each
  successful release.

### Scoping note — 2026-07-17

The checklist above predates `stack release`. Before building it, reconcile it
with what already ships.

**Already built.** `mq_agent/tools/stack_release.py` implements single-repo
release automation end to end: `plan_stack_release` (gate + clean-tree +
on-main + unreleased-commits + semver check) and `execute_stack_release`
(bump-version → sync-contract → update-changelog → commit → tag → push →
truth-export, with rollback of pre-commit edits on any failed step). The
planned `mq-agent release plan|prepare|execute` items are largely this under
new names — building them as specified would duplicate `stack release`, the
exact consumer-before-producer / duplicate-work pattern this stack has now hit
four times.

**The real gap this session surfaced.** Each repo also carries its own
`release.sh`, and that path — not `stack release` — is the one operators used.
`release.sh` bumps `VERSION` but never `.mq/repo-contract.json`, so three repos
shipped tags (`macos-scripts v1.0.1`, `mq-mcp v2.0.1`, `repo-signal v1.4.1`)
with the contract one version behind, each tagged off a feature branch and
never merged to `main`. The drift stayed invisible because those repos had no
contract-version gate. Gates now exist across the stack (mq-agent#135,
mq-hal#15, mq-mcp#45, repo-signal#14, and the pointer check on macos-scripts
main), so drift fails a repo's own CI instead of mq-agent's stack gate — but a
gate only catches drift after the fact. It does not stop the two-path,
tagged-off-main release shape that produced it.

**Recommended reframe.** Point v1.23.0 at making the correct path the only
path, not at rebuilding the plan/prepare/execute surface:

* [ ] Converge the release paths: either retire each repo's `release.sh` in
  favour of `stack release`, or make `release.sh` sync `.mq/repo-contract.json`
  through the same logic, so the contract cannot drift regardless of which path
  runs.
* [ ] Add multi-repo orchestration over the existing single-repo primitive
  (`stack release` is one repo at a time) — refuse any repo that is dirty, off
  main, or already tagged at the target version.
* [ ] Enforce on-main releases: a tag cut off a feature branch that never
  reaches `main` is the failure mode that produced the current drift.
* [ ] Decide the disposition of the three botched tags (`v1.0.1`, `v2.0.1`,
  `v1.4.1`) — leave as known-bad history, or delete and re-release cleanly
  through `stack release`. Tag deletion is destructive and is the operator's
  call.

## v1.15.0 — Brain-integrated stack workflow

Goal: make mq-agent the stable conductor of the full loop —
repo status → review → learn extract → brain write → stack truth export
→ next action. mq-agent orchestrates; mq-mcp thinks/runs, repo-signal
measures, mqobsidian remembers, mqlaunch launches.

* [x] `mq-agent stack cockpit` — one table for the whole stack:
  repo, status, branch, dirty, version, contract, release gate,
  brain export freshness, next action. Later the input to mq-hal.
* [x] Consistent flag behaviour across write-capable commands:
  `--dry-run` never writes, `--json` machine-readable, `--brain`
  never writes without an explicit command, `--approve` required
  for write flows.
* [x] Standard mqobsidian export structure: `memory/stack-truth/`,
  `memory/reviews/`, `memory/learn/`, `mq-stack/runs/`, `mq-stack/roadmaps/`
  — `mq-agent brain structure` (check / `--init --approve`)
* [x] Brain release gate: `mq-agent stack brain-gate` — `contract-check` +
  `release-check` + truth-export dry-run + vault structure + the
  review→brain write path, all green before release
* [x] Docs sync: README, docs/ROADMAP, MQ_ECOSYSTEM, CHANGELOG, repo-contract
* [x] Tag v1.15.0

## v1.14.0 — Stack release orchestration

Goal: close the loop. The stack suite observes (`status`, `report`, `sweep`,
`history`), gates (`alert`, `release-check`, `contract-check`), remembers
(`truth-export`), and drafts (`release-notes`) — but the release itself is
still manual, per repo, across 7 repos. `stack release` makes the pipeline act.

* [x] `mq-agent stack release --repo <name>` — orchestrated single-repo release:
  release-check as pre-gate, version bump, changelog update from the
  release-notes draft, tag, push
* [x] Dry-run by default (same pattern as `sweep`); `--execute` to apply
* [x] `--json` — machine-readable output for CI
* [x] Automatic `truth-export` after a successful release, so the release
  lands in mqobsidian memory
* [x] Abort cleanly on any failed step — no half-released repos
* [x] `docs/STACK_RELEASE.md` — reference doc
* [x] Tests for gate refusal, dry-run plan, step failure rollback (27 tests)
* [x] Tag v1.14.0

## v1.13.0 — mqobsidian stack truth export

Goal: turn stack gate results into durable mqobsidian memory, not transient CI logs.

* [x] `mq-agent stack truth-export` — truth note from contract-check + release-check
* [x] `mq-agent stack export` kept as backwards-compatible alias
* [x] Dated default note path under `~/mqobsidian/memory/stack-truth/`
* [x] `--ci` mode for stack gates; two-job CI workflow (fast PR gate + full stack gate)
* [x] 25 new tests (439 total)
* [x] Tag v1.13.0

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full release history.
