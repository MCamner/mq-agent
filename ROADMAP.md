# mq-agent Roadmap

Released: v1.25.1 — Release Cockpit post-release audit fix.
Next: v1.26.0 — Stack Compatibility Gate.

## Current status

All release phases complete through v1.25.1.

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
| v1.23.0 | Cross-repo release automation | Released v1.23.0 |
| v1.24.0 | PR-mediated release flow | Released v1.24.0 |
| v1.24.1 | Post-release stabilization | Released v1.24.1 |
| v1.25.0 | Release Cockpit | Released v1.25.0 |
| v1.25.1 | Release Cockpit post-release audit fix | Released v1.25.1 |
| v1.26.0 | Stack Compatibility Gate | In progress |

## Completed — v1.24.1 Post-release stabilization

The release path now supports `direct`, `pull_request`, and `manual` contract
modes. This release aligned dry-run planning, execution policy, contract-check
coverage, and operator documentation.

* [x] Make single-repo dry-run plans release-mode aware.
* [x] Include `mqobsidian` in contract-check coverage.
* [x] Document prepare, merge, finalize, and direct/manual behavior.
* [x] Set current direction to post-v1.24 stabilization.
* [x] Restore a green repo-wide Ruff baseline.
* [x] Centralize release-mode policy used by single- and multi-repo flows.

## Completed — v1.25.0–v1.25.1 Release Cockpit

Released 2026-08-10. v1.25.1 fixed the post-release audit classification so
an aligned published release resolves to `AUDITED` rather than treating its
existing tag and lack of unreleased commits as prepare blockers.

### Product direction

v1.24.1 proved the PR-mediated release chain end to end. v1.25 made that safe
machinery understandable from one operator-facing surface: `mq-agent` shows
the current release state, explains blockers in plain language, and recommends
exactly one safe next action.

The release engine already exists. v1.25.0 improves the experience around it;
it does not introduce another release mechanism.

### Goals

#### 1. Add `mq-agent ship status`

* [x] Add a read-only `mq-agent ship status` command.
* [x] Show repository, current and target versions, latest tag and target,
  local `main` state, CI state, release-check, contract-check, stack preflight,
  open release PR, and GitHub Release state.
* [x] Make the default output answer: “Can I release safely right now?”
* [x] Add a stable `--json` representation for future CI and `mqlaunch`
  consumers.

#### 2. Define one release state model

* [x] Define and test these states:
  `IDLE`, `BLOCKED`, `PREFLIGHT_READY`, `PREPARED_PR`, `PR_GREEN`, `MERGED`,
  `FINALIZED`, `PUBLISHED`, and `AUDITED`.
* [x] Give states an explicit precedence so one snapshot cannot resolve to
  multiple states.
* [x] Require a target version before reporting `PREFLIGHT_READY`; aligned
  current version and tag without a target remains `IDLE`.
* [x] Treat `AUDITED` as a verified snapshot, not permanent stored truth.

State meanings:

| State | Meaning |
| --- | --- |
| `IDLE` | No target release is in progress; current version and tag align |
| `BLOCKED` | At least one safety prerequisite prevents progress |
| `PREFLIGHT_READY` | A target exists and all prepare prerequisites pass |
| `PREPARED_PR` | A release PR exists; no release tag exists |
| `PR_GREEN` | The release PR is open, reviewed as required, and CI is green |
| `MERGED` | The release PR is merged; the release tag does not yet exist |
| `FINALIZED` | The annotated tag exists and targets the verified mergecommit |
| `PUBLISHED` | Tag, GitHub Release, and version surfaces align |
| `AUDITED` | A post-release audit currently passes without blockers |

#### 3. Recommend exactly one next action

* [x] Return one deterministic next action for every state.
* [x] Include a copy-pasteable command only when the action is local and safe
  for the current state.
* [x] Return `No action needed` when the latest release is audited.
* [x] Keep human review and merge decisions explicit; do not present them as
  automatic execution.

#### 4. Explain blockers in operator language

* [x] Map dirty or missing repos, failed CI, failed release or contract gates,
  blocked stack preflight, existing tags, an unmerged release PR, a wrong tag
  target, and a missing GitHub Release to bounded explanations.
* [x] Include the affected repo or release identifier when known.
* [x] Preserve the underlying machine-readable reason in JSON output.
* [x] Do not hide partial or unavailable checks behind a green summary.

#### 5. Add `mq-agent ship proof`

* [x] Add a read-only proof view for the current or selected release.
* [x] Include version, release PR, mergecommit, tag name and type, tag target,
  GitHub Release status and URL, CI status, release and contract checks, stack
  preflight, and local `main` cleanliness.
* [x] Add `--json`.

#### 6. Add `mq-agent ship audit`

* [x] Verify that local `main` is clean and synced with `origin/main`.
* [x] Verify version surfaces, latest tag, annotated tag target, GitHub
  Release, main CI, release-check, contract-check, and zero preflight blockers.
* [x] Remain read-only by default.
* [x] Add `--json` with evidence for every check.

#### 7. Keep `stack release` as the engine

* [x] Reuse existing release planning, contract, preflight, prepare, and
  finalize primitives instead of duplicating policy.
* [x] Keep `stack release` as the lower-level implementation surface.
* [x] Keep the first `ship` release read-only: status, proof, and audit only.
Optional `ship prepare`, `ship finalize`, and `ship publish` wrappers are
deferred until operational use shows that wrappers improve safety without
hiding the lower-level release evidence.

### Non-goals

* [x] No new release mechanism.
* [x] No automatic merge or automatic post-merge finalize.
* [x] No GitHub Release publication without explicit approval.
* [x] No unrelated lint or cleanup work.
* [x] No replacement of technical evidence with simplified status text.

### Definition of done

* [x] `mq-agent ship status`, `ship status --json`, `ship proof`, and
  `ship audit` exist.
* [x] State precedence, blocker mapping, and next-action selection are tested.
* [x] Existing `stack release` behavior remains unchanged.
* [x] PR-mediated releases cannot tag before a verified merge.
* [x] Documentation names `ship` as the operator surface and `stack release`
  as the engine.
* [x] README, command-surface docs, public roadmap, and GitHub Pages index are
  synchronized when the commands ship.
* [x] Main CI, release-check, contract-check, and stack preflight pass without
  blockers.

### Recommended implementation order

1. State model, `ship status`, and JSON contract.
2. Plain-language blockers and deterministic next action.
3. `ship proof` and `ship audit`.
4. Command reference, release-cockpit guide, README, and Pages links.

## Next release — v1.26.0 Stack Compatibility Gate

* **Status:** In progress — Phase 0 through Phase 5 delivered in `mq-agent`,
  plus release-gate enforcement from Phase 6;
  the `mq-hal` and `mqlaunch` surfaces are owned by those repos
* **Priority:** P1
* **Owner:** `mq-agent`
* **Consumers:** `mq-hal`, `macos-scripts`, CI
* **Contract:** `mq.stack-compatibility.v1`

### Problem

Individual MQ repositories can be green while the stack still contains a
latent incompatibility.

This happened when `mq-image-analyze` and `mq-mcp` used the same removed
FastMCP import and both allowed MCP 2.x. `mq-image-analyze` failed after its
dependencies were resolved again. `mq-mcp` remained green only because
`uv.lock` kept MCP 1.27.1 in place.

Repository-specific tests and lockfiles therefore cannot prove on their own
that:

* declared dependency ranges match known API contracts;
* locked versions remain within declared ranges;
* two MQ repositories use compatible versions of a shared protocol;
* a fresh dependency resolution will not break the stack; or
* consumers and producers use the same contract version.

### Goal

Introduce a read-only, deterministic compatibility command:

```bash
mq-agent stack compatibility
mq-agent stack compatibility --json
mq-agent stack compatibility --fresh-resolve
```

The command should detect dependency and contract drift across repository
boundaries before it reaches installation, release, or runtime.

### Ownership and boundaries

* `mq-agent` owns orchestration, aggregation, and the final assessment.
* Each repository owns its declared dependencies and compatibility metadata.
* `.mq/repo-contract.json` is the repository's machine-readable input.
* `mqobsidian` documents stack architecture but does not own runtime status.
* `mq-hal` may read and present the result but must not duplicate the logic.
* `macos-scripts` may delegate to the command but must not implement its own
  compatibility assessment.
* The command must not modify dependencies, lockfiles, or working trees.
* Missing repositories, tools, or metadata must be reported as `UNAVAILABLE`.

### Phase 0 — Contract and scope

**Deliverable:** `mq.stack-compatibility.v1`

* [x] Define the JSON schema for compatibility reports.
* [x] Reuse `PASS`, `WARN`, `FAIL`, `SKIPPED`, and `UNAVAILABLE`.
* [x] Define structured evidence and `next_action`.
* [x] Distinguish declared, locked, installed, mutually compatible, and freshly
  resolved versions.
* [x] Define stable error and warning codes.
* [x] Document which findings block release.
* [x] Add schema and negative contract tests.

Example:

```json
{
  "schema": "mq.stack-compatibility.v1",
  "status": "WARN",
  "components": [],
  "relationships": [],
  "findings": [],
  "next_action": "Declare the actual compatibility boundary in mq-mcp"
}
```

#### Definition of done

* The schema is versioned.
* Human and JSON output have identical semantics.
* Unknown status values and incomplete evidence are rejected.
* No runtime or repository changes are performed.

### Phase 1 — Repository inventory

**Deliverable:** discovery of MQ repositories and compatibility metadata.

* [x] Discover active MQ repositories from configuration or explicit paths.
* [x] Read `.mq/repo-contract.json`.
* [x] Read supported dependency sources, including `pyproject.toml`, `uv.lock`,
  and `constraints.txt`.
* [x] Identify each repository's version and role.
* [x] Report missing or invalid contracts.
* [x] Preserve repository, file, field, and observed value as provenance.
* [x] Support `mq-mcp` and `mq-image-analyze` as the first vertical slice.

#### Definition of done

* Both MCP repositories are discovered without hardcoded private paths.
* Declared and locked MCP versions are reported correctly.
* Missing repositories or files produce `UNAVAILABLE`.
* The command is read-only and supports `--json`.

### Phase 2 — Declared compatibility

**Deliverable:** machine-readable compatibility data in repository contracts.

Proposed structure:

```json
{
  "compatibility": {
    "protocols": {
      "mcp_api": "1.x-fastmcp"
    },
    "dependencies": {
      "mcp": ">=1.27.1,<2"
    },
    "produces": ["mq-mcp.tools.v1"],
    "consumes": ["mq.feedback.v1"]
  }
}
```

* [x] Extend the repository contract without breaking existing consumers.
* [x] Declare critical protocols and dependency boundaries.
* [x] Declare produced and consumed MQ contracts.
* [x] Validate declarations against `pyproject.toml`.
* [x] Validate that locked versions fit declared ranges.
* [x] Distinguish missing metadata from inconsistent metadata.

The gate reads and enforces the block. Declaring it in `mq-mcp` and
`mq-image-analyze` is a separate change in those repos.

#### Definition of done

* `mq-mcp` and `mq-image-analyze` declare the MCP 1.x contract.
* A locked version outside the declared range produces `FAIL`.
* An open range that contradicts the API contract produces `FAIL`.
* Missing optional metadata remains explicit and non-blocking during rollout.

### Phase 3 — Stack relationships and overlap

**Deliverable:** compatibility checks between producers and consumers.

* [x] Match produced and consumed contracts.
* [x] Calculate overlap between shared dependency ranges.
* [x] Detect parallel protocol tracks in the same stack.
* [x] Detect consumers requiring a contract no producer offers.
* [ ] Detect producer schema changes without corresponding consumer updates.
* [ ] Check MCP tool names, safety classes, and schema signatures.
* [x] Present relationships as evidence, not only a summary status.

Example finding:

```text
FAIL  mq-mcp ↔ mq-image-analyze
      Shared protocol: MCP
      mq-mcp API contract: 1.x-fastmcp
      mq-image-analyze API contract: 1.x-fastmcp
      Declared dependency ranges overlap: yes
      Unbounded major-version exposure: no
```

#### Definition of done

* Known compatible ranges produce `PASS`.
* Ranges without overlap produce `FAIL`.
* Different MCP tracks produce at least `WARN`, or `FAIL` on one runtime path.
* Every assessment includes source files and observed values.

### Phase 4 — Fresh resolve

**Deliverable:** an isolated check of what a new installation would select.

```bash
mq-agent stack compatibility --fresh-resolve
```

* [x] Run only when explicitly requested.
* [x] Create temporary environments outside repository working trees.
* [x] Never modify existing lockfiles.
* [x] Resolve dependencies from declared specifications.
* [x] Compare freshly resolved and locked versions.
* [x] Test critical imports and bounded, declared contract smokes.
* [x] Clean temporary environments after the run.
* [x] Support timeouts and explicit network-error handling.
* [x] Report network or registry failures as `UNAVAILABLE`, not incompatibility.

Initial critical import:

```python
from mcp.server.fastmcp import FastMCP
```

Import probes are declared by each repository under
`compatibility.import_probes`; the central map is only the fallback for repos
that have not declared theirs.

#### Definition of done

* MCP 2.x resolved against a FastMCP 1.x contract produces `FAIL`.
* An older lockfile cannot make the result green on its own.
* Working trees and real lockfiles remain unchanged.
* Network failures remain distinguishable from incompatibility.

### Phase 5 — CLI, dashboard, and CI

**Deliverable:** operator surfaces and automated gates.

* [x] Add `stack compatibility`, `--json`, and `--fresh-resolve`.
* [x] Show the summary in `mq-agent dashboard`.
* [ ] Expose the result read-only through `mq-hal`. Owned by `mq-hal`.
* [ ] Delegate from `mqlaunch` without duplicated logic. Owned by
  `macos-scripts`.
* [ ] Run static checks in relevant PR and release workflows. Deliberately not
  on pull requests: only the checkout exists there, so every sibling reports
  `UNAVAILABLE` and the gate says nothing. It runs on push to `main`.
* [x] Run fresh resolution on a schedule or before release.
* [x] Preserve exit codes and human/JSON parity.
* [x] Document which statuses block merge or release.

Proposed exit codes:

* `0` — `PASS`
* `1` — `WARN` in strict mode
* `2` — `FAIL`
* `3` — `UNAVAILABLE`
* `130` — interrupted

#### Definition of done

* CLI, JSON, and dashboard show the same findings.
* `mq-hal` and `mqlaunch` delegate to `mq-agent`.
* CI distinguishes incompatibility from an unavailable check.
* No surface performs automatic dependency upgrades.

### Phase 6 — Extend across the MQ stack

* [x] Enforce `blocks_release` in `stack release-check` and the release
  cockpit. Both read the static check only and refuse a release for every
  repository a blocking finding implicates; a report that could not be
  produced is `UNAVAILABLE` and blocks nothing. Pairwise findings gained a
  `repos` list, because naming only the left-hand repo blocked one half of an
  incompatible pair and let the other half release.
* [ ] Add `mq-agent`, `mq-hal`, `repo-signal`, `macos-scripts`, and
  `mqobsidian`.
* [ ] Add `mq-ums` where machine-readable contracts exist.
* [ ] Check shared Python and JSON contracts.
* [ ] Check versioned observations, feedback, and memory schemas.
* [ ] Add regression fixtures for previous real drift failures.
* [ ] Document exceptions for components using different package managers or
  runtimes.

### First regression case

Preserve the MCP incident as a fixture:

* both repositories import FastMCP from MCP 1.x;
* both declare an open range that accepts MCP 2.x;
* one repository has no protective lock;
* the other has an older locked version;
* local CI is green in the locked repository; and
* the stack check must still report the exposure.

The fixture must distinguish **works with today's lock** from **declares a
genuinely compatible future resolution**.

### Non-goals

The first version will not:

* migrate a server to MCP 2.x;
* update dependencies or rewrite lockfiles automatically;
* replace repository-specific tests or duplicate `repo-signal`;
* interpret every package manager;
* infer compatibility without evidence;
* make GitHub changes; or
* make `mqobsidian` a runtime authority.

### Proposed PR series

1. **Contract:** schema, models, and negative tests.
2. **Inventory:** repository discovery and dependency/lock data for `mq-mcp`
   and `mq-image-analyze`.
3. **Compatibility:** API declarations, range overlap, and locked-versus-
   declared checks.
4. **Fresh resolve:** temporary resolution, import probes, and read-only gates.
5. **Surfaces:** CLI, dashboard, `mq-hal`, and `mqlaunch` delegation.
6. **CI and expansion:** PR/release gates, the MCP regression fixture, and
   incremental support for the remaining repositories.

### Final definition of done

* [ ] `mq-agent stack compatibility` works without network access.
* [ ] `--json` conforms to `mq.stack-compatibility.v1`.
* [ ] `--fresh-resolve` changes no repositories or lockfiles.
* [ ] Latent major-version exposure is detected even when the lockfile is green.
* [ ] Producer and consumer contracts are compared across repositories.
* [ ] Every assessment contains evidence and `next_action`.
* [ ] Human, JSON, dashboard, and HAL results are semantically identical.
* [ ] `mqlaunch` and `mq-hal` duplicate no compatibility logic.
* [ ] The MCP regression case remains permanently tested.
* [ ] Documentation, command references, and architecture maps are updated.
* [ ] The full `mq-agent` suite and relevant stack contracts are green.

### Recommended starting point

Start with PR1 and PR2 only. They provide a stable contract and measurable,
network-free inventory without dependency installation or changes in other
repositories. Do not activate a blocking CI gate until it has run in shadow
mode and false positives have been reviewed.

## Deferred work

### Optional `ship` write wrappers

Do not add `ship prepare`, `ship finalize`, or `ship publish` in v1.26. The
read-only cockpit contract is stable, but the existing `stack release` engine
already owns mutation and approval policy. Reconsider wrappers only with
operator evidence that they reduce mistakes without obscuring proof.

### Inbox evidence ingestion

Accepting `repo-signal` readiness and `mq-mcp` review output as inbox evidence
remains blocked on producer-owned, candidate-bearing bounded JSON with explicit
`producer` and `schema_id`. `mq-agent` must not invent those upstream contracts.

## Historical release archive

The sections below preserve completed milestones, superseded checklists, and
implementation checkpoints. They are historical evidence, not active work.

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
* Deferred upstream evidence ingestion is tracked under **Deferred work**;
  v1.22 shipped without taking ownership of producer contracts.
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

### v1.23.0 checklist (superseded — do not work through this list)

**Superseded 2026-07-17 by the reframe below.** This list predates `stack
release` and most of it would rebuild what already ships. It is kept for
provenance only; the live checklist is under *Recommended reframe*. The
unchecked boxes here are not open work.

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

### Agent context pipeline — Claude/Codex optimization

Goal: make Claude/Codex grounding fast and low-cost by prioritizing compact,
controlled exports before falling back to the full `mqobsidian` vault.

* [x] Run `mq-agent agent-views rebuild` as the first prepare step
  * Explanation: builds `memory/learn/agent/<system>.md` from `hot.md` + `index.md`.
  * Result: model step‑0 view; small, focused first-read surface.
* [x] Export `.mq/context/*` snapshots for relevant repos
  * Explanation: `mq-agent context export --repo <repo> --output-root <dir>`
  * Result: repo-local `repo-card.md`, `integration-map.md`, `token-budget.md`, `active-contract.md`.
* [x] Prioritize read order in agent workflows
  * Explanation: prefer `memory/learn/agent` → `.mq/context/*` → full vault as fallback.
  * Result: reduced token usage, faster grounding, less noise.
* [x] Add drift guard in CI/prep
  * Explanation: `mq-agent agent-views check` fails when views are stale.
  * Result: CI can refuse runs when generated views are out of sync.
* [ ] Create a repeatable prepare step (script/CI target)
  * Explanation: combine rebuild + export into one `prepare-context` step.
  * Result: deterministic, reproducible context preparation for all agent runs.

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
never merged to `main`. (Correction 2026-07-19: `macos-scripts v1.0.1` does not
hold up on inspection — see the tag-disposition item below. Only `mq-mcp
v2.0.1` and `repo-signal v1.4.1` were actually drifted.) The drift stayed
invisible because those repos had no contract-version gate. Gates now exist
across the stack (mq-agent#135, mq-hal#15, mq-mcp#45, repo-signal#14, and the
pointer check on macos-scripts main), so drift fails a repo's own CI instead of
mq-agent's stack gate — but a gate only catches drift after the fact. It does
not stop the two-path, tagged-off-main release shape that produced it.

**Recommended reframe.** Point v1.23.0 at making the correct path the only
path, not at rebuilding the plan/prepare/execute surface:

* [x] Converge the release paths: either retire each repo's `release.sh` in
  favour of `stack release`, or make `release.sh` sync `.mq/repo-contract.json`
  through the same logic, so the contract cannot drift regardless of which path
  runs. Done — each repo's `release.sh` now syncs the contract (or validates
  it): mq-mcp #46, macos-scripts #55, repo-signal #15.
* [x] Add multi-repo orchestration over the existing single-repo primitive
  (`stack release` is one repo at a time) — refuse any repo that is dirty, off
  main, or already tagged at the target version. `stack release --all` (#141)
  aggregates the per-repo plan; the plan refuses dirty and off-main, and now
  also refuses a target version whose tag already exists locally or on origin —
  the drift shape that would otherwise abort mid-release after the commit.
* [x] Enforce on-main releases: a tag cut off a feature branch that never
  reaches `main` is the failure mode that produced the current drift. The plan
  blocks off-main, and `execute_stack_release` now re-verifies on-main and a
  clean tree against the live repo before any mutation — so a plan built on main
  cannot cut a tag once the checkout has moved off main or gone dirty. Broader
  enforcement (server-side branch protection) stays out of scope; this is the
  local release-shape guard.
* [~] Multi-repo execute (`stack release --all --execute`) — design locked in
  [docs/STACK_RELEASE_ALL_EXECUTE.md](docs/STACK_RELEASE_ALL_EXECUTE.md)
  (fail-fast preflight gate, stop-on-first-failure, no destructive rollback).
  Slice 1 **shipped**: the read-only preflight hook `stack release --all
  --preflight` (`preflight_stack_release_all`, schema
  `mq_stack_release_all_execute.v1`) — the full refusal surface incl. each repo's
  `release-check.sh` (`repo_release_check.v1`), never mutates. Slice 2 (per-repo
  `release-check.sh` rollout) **done — 8/8**: mq-agent #147, mq-hal #17,
  mqobsidian #50, repo-signal #17, mq-mcp #48, mq-ums #13, mq-image-analyze #11,
  macos-scripts #57. The five that were off-main in the live drive have since
  landed on `main`; verified by running `release-check.sh --json` in each repo —
  all eight answer with schema `repo_release_check.v1` and status `READY`, and
  `stack release --all --preflight` reports `blocked 0`. Slice 2 is **closed**;
  the rollout needs no further work.
* [x] **Multi-repo execute (`--execute --approve`) — done.**
  `execute_stack_release_all` runs the read-only preflight, fail-fast gates on
  any `BLOCKED` repo before a single mutation, then executes the `READY` repos
  in explicit `MQ_STACK_REPOS` (dependency) order with stop-on-first-failure.
  Repos after a failure are reported `SKIPPED` and never started; an
  already-released repo is left released, because un-releasing it would mean
  deleting a pushed tag or rewriting history. `--execute` without `--approve`
  prints what would be released and touches nothing. Both locked execute-phase
  tests ship with it — repo 2 of 5 fails → 3–5 `SKIPPED`, and the released repo
  keeps its commit and its pushed tag — and the failure is real (one repo is
  given no reachable remote so its `git push` fails mid-run) rather than a
  patched return value.
* [x] Disposition of the drifted tags — **decided 2026-07-19: keep as known-bad
  history and fix forward.** Tag deletion was rejected as destructive; the
  operator's rule for these operations is run from clean `main`, verify the
  target tag does not already exist, no remote tag deletion, no force-push, no
  history rewrite, protected `main` → branch/PR, and stop on any deviation.
  * `mq-mcp v2.0.1` — kept as known-bad. Fixed forward to `v2.0.2`: the package,
    stability, tool-contract and repo-contract surfaces had stayed at `2.0.0`.
    The fix also stopped `tests/test_cli.py` and
    `tests/test_server_observability.py` asserting a hardcoded `"2.0.0"` — they
    read `VERSION` from disk now, which is what let the drift ship.
  * `repo-signal v1.4.1` — kept as known-bad. Fixed forward to `v1.4.2`: the
    repo contract had stayed at `1.4.0`.
  * `macos-scripts v1.0.1` — **not** drifted, contrary to the earlier note
    above. Verified 2026-07-19: annotated tag, an ancestor of `main`, and
    `.mq/repo-contract.json` reads `1.0.1` at the tag, matching `VERSION`.
    Nothing to fix forward; its next release proceeds normally.
  * `stack release --all --preflight` is clean — `blocked 0`.

### Release-mode contract — 2026-07-19

Releasing v1.23.0 exposed a structural gap the design had not modelled.
`stack release --execute` pushes straight to `main`; three stack repos
(`mq-agent`, `macos-scripts`, `mqobsidian`) require a pull request, so the
push was refused with `GH013` **after** the bump, commit and tag already
existed locally. All of it had to be unwound by hand.

The tool knew versions, tags, clean tree, unpushed commits, `release-check.sh`,
README and `uv.lock` — but nothing about whether a repo may be pushed to at
all, so it learned about branch protection by failing at the most expensive
possible point.

* [x] `release_mode` is declared data in `.mq/repo-contract.json`, read before
  any mutation (#157). Execute refuses anything that is not `direct`, and an
  absent field is refusal rather than permission. `--all --preflight` stays a
  pure readiness measurement; the mode gate belongs to the mutating path.
* [x] **PR-mediated release path.** `pull_request` repos use
  release branch → PR → merge → tag the merged SHA, as a first-class flow
  rather than a manual recovery.
* [x] Declare `release_mode` across the configured stack repos.
* [x] Fold README's status badge and status section into the declared version
  surfaces. `stack release` bumps VERSION, pyproject, `uv.lock` and the
  contract; README drifted and only CI's docs job caught it, while
  `release-check.sh --json` still reported `READY`. Two gates, two different
  definitions of releasable.

### Checkpoint — 2026-07-19

State of v1.23.0 at the point the work was paused. Four of five reframed
slices are done: release paths converged, multi-repo dry-run orchestration,
on-main enforcement, and the read-only preflight incl. the 8/8
`release-check.sh` rollout. The tag disposition is decided — `mq-mcp v2.0.1`
and `repo-signal v1.4.1` kept as known-bad, fixed forward to `v2.0.2` and
`v1.4.2`, no tag deletion, no force-push, no history rewrite.

Last preflight run for this checkpoint (`stack release --all --preflight
--json`, schema `mq_stack_release_all_execute.v1`):

```text
ready 7   blocked 0   up-to-date 1
would_execute true    aborted_phase none
```

All eight repos are on `main` and clean. `repo-signal` is the up-to-date one
(`v1.4.2` already released). `mq-mcp` reads `READY 2.0.2 -> 2.0.3` rather than
up-to-date because of one docs commit landed after its tag (#50) — expected,
not drift.

Only the execute slice remains open, and it is deliberately a separate work
session. This checkpoint added no wiring, no tags, and ran no releases.

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
