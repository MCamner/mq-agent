# mq-agent Roadmap

mq-agent is a terminal-native workflow orchestration runtime for the mq ecosystem.

It connects safe local execution, repo intelligence, MCP tools, mqlaunch workflows,
and semantic repository memory into one controlled, operator-driven orchestration
surface.

---

## Current status

Current project phase:

```text
v1.7.0 — Repo health history (done)
Next:    v1.8.0 — TBD
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

---

## Completed

### v1.7.0 — Repo health history

* [x] `stack sweep` appends every non-dry-run run to `~/.mq-agent/sweep-history.jsonl`
* [x] `mq-agent stack history` — tabular trend view, last N sweeps
* [x] `mq-agent stack history --diff` — delta table between last two sweeps
* [x] `mq-agent stack history --json` / `--limit N`
* [x] `docs/STACK_HISTORY.md` — reference with JSONL schema and jq examples
* [x] 13 new tests (343 total)

### v1.6.0 — Stack-wide health

* [x] `mq-agent stack sweep` — loop repo-signal over all mq-stack repos in one pass
* [x] `mq-agent stack sweep --brain` — brain note per repo via `_brain_record_review`
* [x] `mq-agent stack sweep --decide` — consolidated ADR via `brain_record_decision`
* [x] `mq-agent stack sweep --dry-run` / `--json` — dry-run and machine-readable output
* [x] mqlaunch agent menu item 18 — Stack health sweep
* [x] `docs/STACK_HEALTH.md` — multi-repo sweep reference with example output

### v1.5.0 — End-to-end demo flow

* [x] `mq-agent signal . --brain` — repo-signal readiness + brain note
* [x] `mq-agent review repo . --brain` — mq-mcp review + brain note
* [x] `mq-agent release-check --dry-run` — contract/release gate
* [x] `mqlaunch/commands/demo-flow.sh` — standalone chain script
* [x] mqlaunch agent menu item 17 — Demo flow (full stack)
* [x] `docs/DEMO.md` rewritten as canonical v1.5.0 reference

### v1.4.0 — mq-image-analyze integration + learn write commands

* [x] `mq-agent run-tool observe_architecture` — delegate to mq-image-analyze
* [x] `mq-agent run-tool image_ocr` — delegate to mq-image-analyze
* [x] `mq-agent review --architecture` includes `visual_architecture_observation.v1` context
* [x] mq-image-analyze tool registration documented in `docs/MQ_ECOSYSTEM.md`
* [x] Smoke tests: mq-agent → mq-image-analyze → structured visual context → mq-mcp
* [x] `mq-agent learn extract-review <path>` — dry-run extraction of learn candidate from last review
* [x] `mq-agent learn review-flow <path>` — orchestrates `review file` + `learn extract-review` in one pass
* [x] `mq-agent learn store <path> --approve` — stores extracted candidate via `record_learning` (Class C)
* [x] `mq-agent learn promote` — promotes a staged learn candidate to a confirmed pattern

### v1.3.0 — Architecture memory, model-selection, learn commands

* [x] Architecture-memory context in review — `list_architecture_decisions` surfaced automatically
* [x] `--fast` flag on `review file/diff/repo` — Class A tool routing via mq-mcp
* [x] `mq-agent learn status / search / explain` — read-only access to learned patterns
* [x] `MultiMCPBridge._call_optional_tool()` — silent None when tool not available
* [x] 292 tests total

### v1.2.0 — mq-mcp semantic memory + risk review routing

* [x] `mq-agent memory search <query>` — calls `search_semantic_memory` via MCPBridge
* [x] `mq-agent memory store <key> <value> --approve` — Class C write, explicit approval
* [x] `mq-agent review --risk` routes to `risk_review_file / risk_review_diff` (mq-mcp ≥ v1.5.0)
* [x] `mq-agent mcp status` shows semantic memory item count and contract freshness

### v1.1.0 — mq-mcp review runtime integration

* [x] `mq-agent review file / diff / repo` via MCPBridge
* [x] `--security`, `--architecture`, `--risk` flags routed to mq-mcp contracts
* [x] Severity findings passed through unchanged — no local review logic
* [x] `validate_orchestration_contract` in doctor checks
* [x] Architecture-memory context surfaced after review findings

### v1.0.0 — Stable orchestration platform

* [x] Stable CLI surface (`COMMAND_SURFACE.md` as single source of truth)
* [x] Stable config format (`MqAgentConfig`, `~/.mq-agent/config.json`)
* [x] Stable safety model — read-only / suggest / execute / approve gates
* [x] Stable mqlaunch, mq-mcp, repo-signal integrations
* [x] Planner wired to `MqAgentConfig.effective_model()`
* [x] Complete docs, examples, release checklist, protected main, GitHub Pages

### v0.9.0 — Orchestration kernel consolidation

* [x] Planner / executor / verifier / task runner contracts locked
* [x] Orchestration logic extracted from `main.py` → `cli/render.py` + `core/diagnostics.py`
* [x] `MqAgentConfig` dataclass and config schema
* [x] 229 tests

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

### v0.8.0 — Controlled specialist orchestration

* [x] `mq-agent swarm list / plan / run / audit / release-check`
* [x] `AgentManifest` — purpose, safety_class, allowed_tools, requires_approve, failure_behavior
* [x] `SwarmRunner` — dispatches agents, collects results, handles failures per manifest
* [x] Built-in swarm configs: `audit`, `release-check`, `ci`
* [x] 190 tests total

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

v1.7.0 is complete. Run a sweep to baseline, then view the trend:

```bash
mq-agent stack sweep
mq-agent stack history
```
