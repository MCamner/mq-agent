# mq-agent Roadmap

mq-agent is a terminal-native workflow orchestration runtime for the mq ecosystem.

It connects safe local execution, repo intelligence, MCP tools, mqlaunch workflows,
and semantic repository memory into one controlled, operator-driven orchestration
surface.

---

## Current status

Current project phase:

```text
v1.4.0 - mq-image-analyze perception tool integration (done)
Next:    v2.0.0 - MQ Skill System + ecosystem orchestration maturity
```

Completed foundation:

* Terminal-native CLI
* Planner / Executor / Verifier architecture
* Safety modes
* Tool registry
* repo-signal integration (v0.7.0+ with version guard)
* mq-mcp bridge (mq-mcp v1.3.0, 66 tools, safety classes A–D)
* mqlaunch integration
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
| v2.0.0  | MQ Skill System + ecosystem orchestration maturity | Active planning |

---

## v1.4.0 — mq-image-analyze perception tool integration

Goal: route mq-image-analyze visual perception tools through mq-agent.
mq-agent delegates image inspection to mq-image-analyze and passes
structured visual context onward to mq-mcp or the user.

Items:

* [x] `mq-agent run-tool observe_architecture` — delegate to mq-image-analyze `observe_architecture` tool
* [x] `mq-agent run-tool image_ocr` — delegate to mq-image-analyze `image_ocr` tool
* [x] Route `mq-agent review --architecture` to include `visual_architecture_observation.v1` context
* [x] Document mq-image-analyze tool registration in `docs/MQ_ECOSYSTEM.md`
* [x] Smoke tests: mq-agent → mq-image-analyze → structured visual context → mq-mcp

Hard boundary (unchanged): mq-agent must never implement image analysis locally.
Delegation and rendering only.

---

## v2.0.0 - MQ Skill System + ecosystem orchestration maturity

Goal: make mq-agent the central owner for MQ Skill System v2.0 and the stable
operator-facing orchestration layer for the mq ecosystem without weakening its
approval-gated execution model.

v2.0.0 starts from the stable v1.4.0 command surface and should focus on
ecosystem-scale orchestration contracts, MQ Skill System ownership and operator
UX maturity.

Contract baseline:

* MQ Skill System v2.0 contracts are defined in
  [MQ_SKILL_SYSTEM.md](MQ_SKILL_SYSTEM.md)
* Implement command behavior only after contract-shape tests and dry-run
  behavior are defined

Implementation order:

1. [x] Define MQ Skill System v2.0 contracts and ownership boundaries
2. [x] Add read-only discovery of repo-local `SKILLS.md` files
3. [x] Normalize discovered skills into `mq.skill.v1` records
4. [x] Add dry-run skill routing preview with JSON output
5. [x] Add ecosystem skill summaries across configured repos
6. [x] Add approval-gated execution only for existing command surfaces
7. [x] Add migration notes and command docs for implemented behavior

Skill-layer readiness gates:

* [x] Inventory cleanup: every active MQ repo has `SKILLS.md`, every listed
  skill path exists, and stale references are removed
* [x] Trigger optimization: stable skills have trigger-strong descriptions with
  should-use and should-not-use cases
* [x] Evals: priority skills have realistic should-trigger and
  should-not-trigger prompts
* [ ] Output contracts: operational skills define predictable human-readable
  and JSON-friendly output shapes
* [ ] Cross-repo routing matrix: common user intents map to the owning repo and
  skill, with overlap and escalation rules
* [ ] Validation tooling: release checks can detect broken skill paths, missing
  metadata, missing evals and stale repo references
* [ ] Skill quality review: stable skills are scored for trigger clarity,
  responsibility boundary, output format, verification and overlap risk

Candidate scope:

* [ ] MQ Skill System v2.0: cross-repo skill discovery, trigger quality, eval
  standards, output contracts and ownership boundaries
* [ ] Repo-local `SKILLS.md` files remain local skill indexes; mq-agent owns the
  central routing, validation and ecosystem summary behavior
* [ ] Stable cross-repo orchestration contracts for mq-mcp, repo-signal, mq-hal,
  mqlaunch, mq-image-analyze and future mq tools
* [ ] Versioned task/workflow manifest format with compatibility checks
* [ ] Stronger ecosystem status and health summaries across configured repos
* [ ] Better operator UX for dry-run, approval, execution, rollback notes and audit
* [ ] Clear migration notes from v1.x command behavior to v2.0.0 behavior

### 8-week prioritized ecosystem track

This track connects the completed `mq-agent` v1.4.0 perception integration with
the next cross-repo work: `mq-mcp` Release Gate v2 and operator-visible review,
validation and release decisions.

North star:

```text
repo / endpoint / screenshot
        ↓
structured signal
        ↓
mq-agent orchestration
        ↓
mq-mcp deterministic review + release gate
        ↓
operator-visible decision
```

The priority is trusted decision flow, not more tools.

#### Week 1 — boundaries and Release Gate v2 contract

Goal: lock architecture before adding features.

* [x] Define the post-v1.4.0 boundary between perception input, review routing
  and operator-facing summaries
* [ ] Add or refresh `docs/V1_4_0_SCOPE.md`
* [ ] Add or refresh `docs/PERCEPTION_INTEGRATION.md`
* [x] Coordinate with `mq-mcp` on `docs/RELEASE_GATE_V2.md`
* [x] Coordinate with `mq-mcp` on `contracts/release_gate_v2.schema.json`

Release Gate v2 should answer:

```text
Can this repo be released safely right now?
Why / why not?
What blocks release?
What should be fixed first?
```

#### Week 2 — perception input contract

Goal: make screenshots, OCR, UI images and diagrams usable as structured review
input.

Normalized perception object:

```json
{
  "source_type": "screenshot | diagram | ui | terminal | browser",
  "source_path": "path/to/image.png",
  "ocr_text": "...",
  "visual_summary": "...",
  "detected_regions": [],
  "risk_signals": [],
  "confidence": "low | medium | high"
}
```

* [ ] Keep `mq-image-analyze` as owner of OCR, screenshot analysis and visual
  summaries
* [x] Keep `mq-agent` as owner of perception routing and review orchestration
* [x] Add or stabilize perception adapter surfaces:
  `mq_agent/perception/adapter.py` and `mq_agent/perception/contract.py`
* [ ] Coordinate read-only `mq-mcp` support for perception review and perception
  contract checks

#### Week 3 — unified review orchestration

Goal: make `mq-agent` the clear orchestrator for file, diff, repo, perception
and release readiness reviews.

Candidate command surface:

```bash
mq-agent review file <path>
mq-agent review diff
mq-agent review repo
mq-agent review perception <image>
mq-agent review release
```

Implemented so far:

* [x] `mq-agent review perception <image>`
* [x] `mq-agent release status`
* [x] `mq-agent release gate`
* [x] `mq-agent release explain`
* [x] `mq-agent dashboard`
* [ ] `mq-agent review release`
* [x] Full stack-health dashboard

Boundary:

```text
mq-agent decides workflow.
mq-mcp performs deterministic review.
mq-image-analyze performs visual extraction.
repo-signal performs repo intelligence.
```

#### Week 4 — Release Gate v2 engine

Goal: turn Release Gate v2 into executable checks owned by `mq-mcp`.

Required check areas:

| Area          | Check                                     |
| ------------- | ----------------------------------------- |
| Tests         | unit tests pass                           |
| Lint/type     | lint and type checks pass                 |
| Docs          | README, ROADMAP, CHANGELOG updated        |
| Contracts     | tool contracts valid                      |
| Safety        | no unsafe command drift                   |
| Versioning    | version bump consistent                   |
| Perception    | visual/review artifacts valid if included |
| Repo quality  | repo-signal export clean                  |
| Release notes | release summary generated                 |

Example command:

```bash
mq-mcp release-gate run --repo . --profile v2
```

The output should be both machine-readable and human-readable, with status,
score, blockers, warnings and next actions.

Implemented so far:

* [x] `mq-mcp release-gate run --repo . --target <version>`
* [x] Release Gate v2 JSON schema
* [x] Machine-readable output with status, score, blockers, warnings and next actions
* [x] Human-readable Release Gate v2 output
* [x] P0 checks for tests, version, changelog, README, ROADMAP, contracts,
  safety classes and release notes
* [x] Perception artifact validation
* [x] repo-signal readiness export integration

#### Week 5 — operator UI first pass

Goal: make the system useful without reading raw JSON.

Start with terminal output before a browser UI.

Candidate commands:

```bash
mq-agent status
mq-agent review dashboard
mq-agent dashboard
mq-agent release status
mq-agent stack health
```

Operator sections:

```text
MQ Stack Health
Release Gate Status
Current Blockers
Perception Findings
Repo Readiness
Suggested Next Action
```

The strongest first outcome is:

```bash
mq-agent release status
```

returning clear operational truth about the target release, Release Gate v2
status, blockers and the recommended next step.

#### Week 6 — cross-repo integration pass

Goal: make the MQ stack work as one system.

| Repo               | Required update                                   |
| ------------------ | ------------------------------------------------- |
| `mq-agent`         | orchestration, perception routing, release status |
| `mq-mcp`           | Release Gate v2 engine                            |
| `mq-image-analyze` | perception output contract                        |
| `repo-signal`      | release/readiness export compatibility            |
| `mq-hal`           | stack status and operator command routing         |
| `macos-scripts`    | mqlaunch entrypoints for review/release workflows |
| `mq-ums`           | later consumer of operator UI patterns            |

Integration pattern:

```text
mqlaunch
   ↓
mq-agent
   ↓
mq-mcp + repo-signal + mq-image-analyze
   ↓
operator decision
```

Document one end-to-end workflow:

```text
mqlaunch → review repo → perception check → release gate → status summary
```

#### Week 7 — hardening and regression safety

Goal: keep the stack from becoming fragile.

Add fixtures where useful:

```text
tests/fixtures/sample_repo_clean/
tests/fixtures/sample_repo_blocked/
tests/fixtures/sample_diff_security_risk.patch
tests/fixtures/sample_ui_screenshot.png
tests/fixtures/sample_perception_output.json
```

Coverage targets:

* [ ] `mq-agent`: review routing, perception adapter, MCPBridge compatibility
  and operator summary rendering tests
* [x] `mq-mcp`: initial Release Gate v2 schema and blocker/warning
  classification tests
* [ ] `mq-mcp`: contract drift and unsafe command detection tests
* [ ] `mq-image-analyze`: output schema compatibility, OCR fallback and
  confidence handling tests

#### Week 8 — release candidate and documentation polish

Goal: ship the release path in a way that looks serious.

`mq-agent` checklist:

```text
README updated
ROADMAP updated
CHANGELOG updated
examples added
commands documented
perception workflow documented
release gate workflow documented
tests green
release notes generated
```

`mq-mcp` Release Gate v2 checklist:

```text
RELEASE_GATE_V2.md complete
schema documented
CLI examples added
sample outputs added
contract table updated
safety classes reviewed
tests green
```

Final demo workflow:

```bash
mq-agent review perception docs/screenshot.png
mq-agent review repo
mq-agent release status
mq-mcp release-gate run --repo . --profile v2
```

### Priority order

P0:

* [x] Define Release Gate v2 contract
* [x] Define perception input/output contract
* [x] Route perception through `mq-agent` without duplicating
  `mq-image-analyze`
* [x] Make `mq-mcp` the deterministic release validator
* [x] Add human-readable release status output

P1:

* [x] Add operator dashboard/status command
* [x] Add initial cross-repo fixture tests
* [ ] Add repo-signal readiness integration
* [ ] Add mqlaunch entrypoint
* [x] Add initial visual/perception review examples

P2:

* [ ] Browser UI
* [ ] Rich HTML reports
* [ ] Historical release score tracking
* [ ] Automatic fix branches
* [ ] GitHub PR comment bot

Recommended repo split:

* `mq-agent` owns workflow orchestration, operator commands, review routing,
  perception routing and release status summaries
* `mq-mcp` owns tool contracts, safety classes, release gate rules, review
  engine, deterministic validation and contract drift detection
* `mq-image-analyze` owns OCR, screenshot analysis, diagram interpretation,
  visual summaries and the perception output contract
* `repo-signal` owns repo readiness, README quality, documentation checks,
  publish readiness and AI context exports
* `mq-hal` owns stack health, natural-language operator routing, safe command
  dispatch and the local status layer

Recommended sequencing:

```text
contracts → routing → release gate → terminal operator UI → browser UI later
```

Non-goals:

* No autonomous execution without operator approval
* No direct implementation of repo-local skills inside mq-agent
* No direct implementation of mq-mcp cognition or mq-image-analyze perception
* No hidden memory upload or repository mutation
* No breaking command changes without migration notes and release checks

---

## Completed

### v0.1.0 — Foundation

* [x] CLI foundation
* [x] Project structure
* [x] Core agent concepts
* [x] Basic docs
* [x] Local development setup

### v0.2.0 — Productization

* [x] README polish
* [x] GitHub Pages front door
* [x] Demo docs
* [x] Safety docs
* [x] Release checklist
* [x] repo-signal scoring
* [x] Publish checklist proof

### v0.3.0 — Local tool orchestration via mq-mcp

* [x] MCP bridge
* [x] MCP status command
* [x] MCP tool listing
* [x] MCP tool safety classes
* [x] Tool metadata inspection
* [x] `run-tool` command
* [x] Docs for MCP integration
* [x] Tests for local tool orchestration

### v0.4.0 — mqlaunch integration

* [x] `mqlaunch agent`
* [x] Direct mqlaunch agent commands
* [x] 12-item mqlaunch agent menu
* [x] 6 direct prompt commands
* [x] smoke test for mqlaunch bridge
* [x] mqlaunch integration docs
* [x] command surface docs
* [x] README proof updates

### v0.4.1 — Consistency, readability and release hygiene

* [x] Source readability pass
* [x] Docs consistency guard
* [x] Command count guard
* [x] `COMMAND_SURFACE.md` as single source of truth
* [x] Release hygiene cleanup
* [x] GitHub release
* [x] GitHub Pages deployment
* [x] Protected `main` workflow

### v0.5.0 — Semantic repository memory

* [x] `mq-agent memory status`
* [x] `mq-agent memory build`
* [x] `mq-agent memory refresh --approve`
* [x] repo-signal semantic upload bridge
* [x] vector store status detection
* [x] dry-run default for memory build
* [x] explicit approval for memory refresh
* [x] semantic memory docs
* [x] memory smoke test
* [x] tests for memory helpers
* [x] README semantic memory section
* [x] GitHub release
* [x] GitHub Pages deployment

---

### v0.5.1 — Semantic memory hardening

* [x] `mq-agent memory doctor` — diagnose environment with per-item status and actionable fixes
* [x] `mq-agent memory doctor --json` — machine-readable diagnostics
* [x] `mq-agent memory status --json` — machine-readable status output
* [x] Example output in `docs/SEMANTIC_MEMORY.md`
* [x] Memory proof section in README with verified output
* [x] `release-check.sh` includes memory smoke
* [x] Missing vector store reported clearly with fix instruction
* [x] Missing repo-signal reported clearly with fix instruction
* [x] Refresh never runs without `--approve`
* [x] 18 CLI-level tests — dry-run default, approval gate, JSON output, doctor diagnostics
* [x] Tests pass locally (94 total)
* [x] GitHub Actions pass
* [x] GitHub release `v0.5.1` exists

---

### v0.6.0 — Controlled agent loops (task runner)

* [x] `mq-agent task list` — list available YAML task workflow files
* [x] `mq-agent task list --json` — machine-readable task list
* [x] `mq-agent task run <name>` — execute declarative YAML workflow via tool registry
* [x] `mq-agent task run <name> --dry-run` — preview steps without execution
* [x] `mq-agent task run <name> --json` — machine-readable step results
* [x] `mq_agent/core/task_runner.py` — `load_task`, `run_task`, `find_task_files`
* [x] Task lookup by filename stem OR internal YAML `name:` field
* [x] `tests/test_task_runner.py` — 18 tests
* [x] Tool registry hardened — `_EXCLUDE_DIRS`, `write_file`, `repo_signal_json`, timeout 120s
* [x] Task YAML args corrected (`suffix→pattern`, `n→limit`, `ci.yml→tests.yml`)
* [x] 134 tests total

---

### v0.6.1 — Orchestration stabilization

* [x] Tool registry hardened — excludes, `write_file`, `repo_signal_json`, timeout 120s
* [x] Task YAML args corrected (`suffix→pattern`, `n→limit`, `ci.yml→tests.yml`)
* [x] `{{step:name}}` template system — string args resolved from prior step output
* [x] `run_task` tool registered — tasks can chain other tasks
* [x] Version guard for repo-signal — clear error when too old
* [x] 204 tests total

---

### v0.7.0 — Browser-assisted workflows

* [x] `mq-agent browser inspect <url>` — structured URL metadata: title, description, h1/h2, links, word count
* [x] `mq-agent browser summarize <url>` — plain-text content summary
* [x] `mq-agent browser verify-release <url>` — release page field verification; `--tag <v>` for version check
* [x] `mq_agent/tools/browser_tools.py` — `fetch_url`, `inspect_url`, `summarize_url`, `verify_release_url`
* [x] URL safety gate: blocks `file://`, `ftp://`, `data:`, `javascript:` schemes
* [x] Browser tools registered in `TOOL_REGISTRY` — usable in task YAML workflows
* [x] `tasks/browser_verify.yaml` — declarative browser verification task
* [x] `tests/test_browser.py` — 27 tests (URL safety, HTML parsing, CLI commands)
* [x] 161 tests total

### Non-goals (v0.7.0)

* No credential handling
* No hidden form submission
* No checkout/payment flows
* No unsafe automation

### Architectural guardrails (v0.7.0)

* Browser workflows must be read-only by default
* No credential capture or storage
* No hidden form submission
* No purchase, booking or account actions
* No autonomous browser control
* All browser actions require explicit operator confirmation
* Browser results must be inspectable and citeable
* Browser workflow logic must use existing task/orchestration systems
* Do not create a second workflow engine

---

### v0.8.0 — Controlled specialist orchestration

This phase coordinates specialized agents through the existing task runner and
safety model. Each agent declares its purpose, safety class, allowed tools, and
failure behavior via `AgentManifest`.

The goal is planner-driven specialization, not autonomous multi-agent behavior.

* [x] `mq-agent swarm list` — list swarm configs with agents and safety classes
* [x] `mq-agent swarm plan <config>` — dry plan; no API, no execution
* [x] `mq-agent swarm run <config> [path]` — execute swarm, unified report
* [x] `mq-agent swarm audit [path]` — audit + signal + docs
* [x] `mq-agent swarm release-check [path]` — CI + audit + release
* [x] `AgentManifest` — declares purpose, safety_class, allowed_tools, requires_approve, output_contract, failure_behavior
* [x] `SwarmRunner` — dispatches agents, collects results, handles failures per manifest policy
* [x] `--approve` gate for write-capable agents
* [x] Dry-run requires no API key
* [x] Built-in swarm configs: `audit`, `release-check`, `ci`
* [x] `tests/test_swarm.py` — 29 tests
* [x] 190 tests total

---

## v0.9.0 — Orchestration kernel consolidation

Goal:

Stabilize orchestration boundaries and normalize runtime coordination before the
v1.0.0 stable release. No new features — only consolidation.

### v0.9.0 focus

* Normalize orchestration lifecycle — planner / executor / verifier contracts
* Unify task execution model — consistent step contracts across task runner and specialist orchestration
* Separate orchestration from presentation — CLI output must not bleed into core logic
* Formalize runtime provider layer — tool registry, MCP bridge, signal integration
* Reduce architectural drift — remove or document any divergent patterns
* Strengthen state consistency — no silent state across step boundaries
* Improve workflow composability — tasks and swarm configs are interchangeable primitives

### Non-goals (v0.9.0)

* No redesign of TUI or CLI surface
* No new autonomous systems
* No additional orchestration modes
* No uncontrolled browser automation
* No duplicate orchestration engines

### v0.9.0 checklist

#### Orchestration lifecycle

* [x] Document the boundary between `PlanStep` (executor loop) and `StepResult` (task runner) — docstrings in `core/state.py`, `core/task_runner.py`, and `test_orchestration_contract.py`
* [x] Document `SwarmRunner` as a separate runtime mode, not a competing implementation of `Executor` — docstring in `core/swarm.py`
* [x] Verify executor stop-on-failure behavior is consistent with task runner error propagation — confirmed by design: executor stops on failure (safety), task runner collects all results (batch)
* [x] Verify `AgentState.to_dict()` output matches JSON output format used by CLI commands — locked by `test_agent_state_to_dict_shape_is_stable()`

#### Presentation separation

* [x] Extract orchestration logic out of `main.py` — `doctor()` logic → `core/diagnostics.py`; rendering helpers → `cli/render.py`
* [x] Centralize status/result rendering — `cli/render.py` owns all Rich output helpers; core has no CLI imports

#### Runtime provider layer

* [x] Define `~/.mq-agent/config.json` schema — `MqAgentConfig` dataclass in `mq_agent/config.py`; schema documented in module docstring
* [x] Wire `Planner` to use `MqAgentConfig` — `load_config().effective_model()` replaces direct env var read
* [x] Enforce tool registry signature contract — `test_tool_registry_has_no_positional_only_params()` passes

#### Contract tests

* [x] Extend `tests/test_orchestration_contract.py` — 7 new shape/delegation tests locking `PlanStep`, `StepResult`, `AgentManifest`, `AgentState`
* [x] Test that `run_task` tool delegates correctly to `task_runner.run_task` — `test_run_task_tool_delegates_to_task_runner()`
* [x] Test that `AgentManifest.allowed_tools` entries are a subset of `TOOL_REGISTRY` keys — `test_agent_manifest_allowed_tools_must_be_subset_of_registry()`

#### Release

* [x] 229 tests pass
* [x] Green CI
* [x] GitHub release `v0.9.0` published

---

## v1.0.0 — Stable orchestration platform

Goal:

Publish mq-agent as a stable, documented orchestration runtime for the mq
ecosystem. The platform is stable when its contracts are locked and its
orchestration boundaries are enforced.

### v1.0.0 requirements

* [x] Stable CLI command surface — `COMMAND_SURFACE.md` is single source of truth
* [x] Stable config format — `MqAgentConfig` dataclass with documented `~/.mq-agent/config.json` schema
* [x] Stable safety model — read-only / suggest / execute / approve gates
* [x] Stable memory model — dry-run default, explicit `--approve`
* [x] Stable mqlaunch integration — bridge tested, menu + direct commands
* [x] Stable mq-mcp integration — start/stop, tool listing, safety classes
* [x] Stable repo-signal integration — version guard, suggest.v1, signal_json
* [x] Stable orchestration contracts — planner / executor / verifier / task runner (v0.9.0)
* [x] Extract orchestration logic from `main.py` — `cli/render.py` + `core/diagnostics.py`
* [x] Wire `Planner` to `MqAgentConfig` — `load_config().effective_model()`
* [x] Complete docs — `ARCHITECTURE.md` updated with full module map, runtime modes, config schema, safety model
* [x] Complete examples — `EXAMPLES.md` covers all commands: task, browser, swarm, memory, mcp, score, signal
* [x] Complete release checklist — `release-check.sh` verified
* [x] Green CI
* [x] Protected main branch
* [x] Versioned GitHub releases — v0.6.0, v0.7.0, v0.8.0 published on GitHub
* [x] GitHub Pages documentation
* [x] No known critical safety gaps

---

## Post-v1.0 roadmap

### v1.1.0 — mq-mcp review runtime integration

Goal: route repo-aware cognition through mq-mcp; mq-agent surfaces findings
without re-implementing review logic.

The formal boundary is defined in
[mq-mcp/docs/ORCHESTRATION_CONTRACT.md](https://github.com/MCamner/mq-mcp/blob/main/docs/ORCHESTRATION_CONTRACT.md):

* mq-agent may auto-invoke Class A/B tools without user confirmation
* Class C (write) and Class D (subprocess) tools require explicit user approval
* mq-agent must never reimplement review logic locally
* mq-agent must not assume mq-mcp maintains session state between calls

Items:

* [x] `mq-agent review` command — calls `review_file` / `review_diff` / `review_repo`
  via MCPBridge; displays severity summary in terminal
* [x] Route `--security` and `--architecture` flags to mq-mcp review contracts
* [x] Route `--risk` only when supported by the installed mq-mcp version
  (v1.5.0 risk layer in mq-mcp)
* [x] Display mq-mcp severity findings (`RISK`, `ARCHITECTURE`, `WARNING`, etc.)
  without reinterpreting — pass through as-is
* [x] `--dry-run` on all review commands — plan output without executing
* [x] Keep TUI/session UX in mq-agent while leaving cognition logic in mq-mcp
* [x] Smoke tests: `mq-agent → mq-mcp review_file / review_diff / review_repo`
* [x] `validate_orchestration_contract` invocable from mq-agent doctor checks
* [x] Surface mq-mcp architecture-memory context (`list_architecture_decisions`,
  `get_architecture_decision`) — shown automatically after review findings when available
* [x] Model-selection policy: `--fast` flag on review commands passes `fast=True` to
  mq-mcp; mq-mcp routes to Class A tools internally

Implementation plan:

1. Add CLI command group:
   * `mq-agent review file <path>`
   * `mq-agent review diff`
   * `mq-agent review repo [path]`
2. Add MCPBridge review helpers:
   * `review_file(path, flags)`
   * `review_diff(flags)`
   * `review_repo(path, flags)`
3. Add pass-through renderer:
   * severity summary
   * grouped findings
   * source file / line when available
   * raw JSON with `--json`
4. Add flags:
   * `--risk`
   * `--security`
   * `--architecture`
   * `--json`
   * `--approve` only if future write-capable review tools require it
5. Add tests:
   * command invokes correct mq-mcp tool
   * no local review logic exists in mq-agent
   * severity labels are passed through unchanged
   * missing mq-mcp tool gives clear error
   * `validate_orchestration_contract` appears in doctor output

Hard boundary:

mq-agent must not implement:

* severity scoring
* architecture reasoning
* risk classification
* semantic retrieval
* review heuristics
* drift detection

mq-agent may implement:

* CLI command routing
* MCPBridge calls
* result rendering
* JSON output
* approval gates
* doctor checks
* orchestration contract validation

v1.1.0 definition of done:

* `mq-agent review file` works through mq-mcp
* `mq-agent review diff` works through mq-mcp
* `mq-agent review repo` works through mq-mcp
* `--json` output is stable and tested
* severity labels are passed through unchanged
* no local review engine exists in mq-agent
* doctor verifies mq-mcp orchestration contract
* smoke tests pass against mq-mcp v1.3.0+
* docs updated:
  * `COMMAND_SURFACE.md`
  * `MCP_INTEGRATION.md`
  * `EXAMPLES.md`
  * `ROADMAP.md`

Non-goals:

* No duplicate review engine in mq-agent
* No architecture reasoning implementation in mq-agent
* No separate semantic retrieval runtime in mq-agent

---

### v1.2.0 — mq-mcp semantic memory + risk review routing

Goal: surface mq-mcp semantic memory (v1.4.0) and risk analysis (v1.5.0) in
mq-agent workflows.

Items:

* [x] `mq-agent memory search <query>` — calls `search_semantic_memory` via MCPBridge;
  renders key/excerpt table; degrades gracefully when mq-mcp v1.4.0 tool is absent
* [x] `mq-agent memory store <key> <value> --approve` — calls `store_semantic_memory`
  (Class C write tool); requires `--approve`; `--dry-run` supported
* [x] Risk review routing: `mq-agent review --risk` invokes `risk_review_file` /
  `risk_review_diff` when available in mq-mcp ≥ v1.5.0 — already implemented in bridge
* [x] `mq-agent mcp status` extended: shows semantic memory item count and contract
  freshness from `validate_orchestration_contract` when tools are available

Learned review patterns (implemented in v1.3.0):

* [x] `mq-agent learn status` — check mq-mcp learn system availability
* [x] `mq-agent learn search <query>` — search learned review patterns
* [x] `mq-agent learn explain <pattern-id>` — fetch pattern explanation

Non-goal:

mq-agent must not train, infer, mutate or store learning data directly. All
learning and memory behavior belongs in mq-mcp.

---

### v1.3.0 — Architecture memory, model-selection, learn commands

* [x] Architecture-memory context in review — `list_architecture_decisions` surfaced
  automatically after review findings when tool is available
* [x] `get_architecture_decision` bridge method for fetching individual decisions
* [x] `--fast` flag on `review file/diff/repo` — passes `fast=True` to mq-mcp for
  Class A tool routing
* [x] `mq-agent learn status` — check mq-mcp learn system
* [x] `mq-agent learn search <query>` — search learned patterns (read-only)
* [x] `mq-agent learn explain <pattern-id>` — fetch pattern explanation (read-only)
* [x] Optional Ollama-backed learn extraction documented as an mq-mcp-owned policy
* [x] `MultiMCPBridge._call_optional_tool()` — silent None when tool not available
* [x] 24 new tests (292 total)

---

## Long-term ideas

These are intentionally not scheduled yet.

* Local model fallback
* Ollama learn provider in mq-mcp
* Visual TUI dashboard
* Repository health history
* Agent-generated release notes
* Agent-generated docs diffs
* Cross-repo ecosystem memory
* Integration with macos-scripts
* Integration with mq-hal
* Integration with mq-ums
* Integration with mq-mcp tool safety map
* Semantic memory comparison between releases

---

## Research / Experimental

These ideas are architecturally interesting but conflict with the current
orchestration philosophy. They are not on the roadmap mainline. Any
implementation must be isolated, gated, and not merged into the core runtime.

* HAL-style conversational shell — autonomous conversational loops break the explicit approval model
* Autonomous looping agents — recursive agent execution without operator checkpoints
* Self-modifying task graphs — tasks that generate and run new tasks at runtime
* Uncontrolled browser automation — beyond operator-approved, read-only browser workflows

---

## Design principles

mq-agent should remain:

* terminal-native
* explicit
* safe by default
* observable
* testable
* local-first
* repo-aware
* dry-run friendly
* approval gated
* useful without hiding execution

The model should assist the operator, not replace the operator.

---

## Safety principles

mq-agent must never:

* run destructive commands silently
* upload memory silently
* commit secrets
* bypass approval gates
* hide shell execution
* treat AI output as automatically trusted
* mutate repositories without explicit approval

Every powerful feature must have:

* dry-run mode
* JSON output when useful
* clear status output
* test coverage
* documentation
* failure behavior

---

## Current recommended next step

Start v2.0.0 planning:

* Start skill-layer readiness gates with inventory cleanup and validation tooling
* Keep routed execution limited to explicit approval and existing command surfaces
* Update `COMMAND_SURFACE.md`, `MCP_INTEGRATION.md` and `EXAMPLES.md` when concrete command behavior changes
* Keep all new orchestration behavior dry-run friendly, approval gated and documented
