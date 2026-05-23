# mq-agent Roadmap

mq-agent is a terminal-native AI agent orchestrator for the mq ecosystem.

It connects safe local execution, repo intelligence, MCP tools, mqlaunch workflows,
semantic repository memory and future agent loops into one controlled command
surface.

---

## Current status

Latest stable release:

```text
v0.5.0 — semantic repository memory
```

Completed foundation:

* Terminal-native CLI
* Planner / Executor / Verifier architecture
* Safety modes
* Tool registry
* repo-signal integration
* mq-mcp bridge
* mqlaunch integration
* Command surface documentation
* Semantic repository memory
* GitHub Pages documentation
* Release hygiene and docs consistency checks
* Protected `main` workflow

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
| v0.5.1  | Semantic memory hardening                    | Next    |
| v0.6.0  | Controlled agent loops                       | Planned |
| v0.7.0  | Browser-assisted workflows                   | Planned |
| v0.8.0  | Multi-agent workflows                        | Planned |
| v1.0.0  | Stable local agent platform                  | Future  |

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

## Next: v0.5.1 — Semantic memory hardening

Goal:

Make semantic repository memory verifiable, observable and safe enough to become
part of the default repo workflow.

### Scope

* [ ] Verify `mq-agent memory status` with real local environment
* [ ] Verify `mq-agent memory build .` dry-run output
* [ ] Verify `mq-agent memory refresh . --approve` with real vector store
* [ ] Add example output to `docs/SEMANTIC_MEMORY.md`
* [ ] Add memory proof section to README
* [ ] Add memory smoke section to release-check output
* [ ] Improve missing dependency messages
* [ ] Improve missing `OPENAI_VECTOR_STORE_ID` guidance
* [ ] Add stale memory concept
* [ ] Add memory freshness metadata
* [ ] Add `mq-agent memory doctor`
* [ ] Add JSON output for memory commands
* [ ] Add tests for failure states
* [ ] Add tests for dry-run behavior
* [ ] Add tests for approval gate behavior

### Proposed commands

```bash
mq-agent memory status
mq-agent memory doctor
mq-agent memory build . --dry-run
mq-agent memory refresh . --approve
mq-agent memory status --json
```

### Definition of done

* [ ] Memory commands work without OpenAI API calls unless explicitly required
* [ ] Missing vector store is reported clearly
* [ ] Missing repo-signal is reported clearly
* [ ] Refresh never runs without `--approve`
* [ ] README includes real memory proof
* [ ] `docs/SEMANTIC_MEMORY.md` includes example output
* [ ] `release-check.sh` includes memory smoke
* [ ] Tests pass locally
* [ ] GitHub Actions pass
* [ ] GitHub release `v0.5.1` exists

---

## v0.6.0 — Controlled agent loops

Goal:

Allow mq-agent to run bounded multi-step workflows while preserving explicit
safety, review and stop conditions.

### Planned scope

* [ ] Loop controller
* [ ] Maximum step count
* [ ] Maximum runtime
* [ ] Stop conditions
* [ ] Per-step verification
* [ ] Failure recovery strategy
* [ ] Human approval checkpoints
* [ ] Loop transcript output
* [ ] `mq-agent loop` command
* [ ] `mq-agent task run <task>` command
* [ ] YAML-defined loop workflows
* [ ] Tests for bounded execution

### Possible commands

```bash
mq-agent loop "improve release readiness" --dry-run
mq-agent task run tasks/release.yaml --approve
mq-agent task status
```

### Non-goals

* No unsupervised destructive actions
* No infinite loops
* No hidden shell execution
* No automatic commits without explicit approval

---

## v0.7.0 — Browser-assisted workflows

Goal:

Add controlled browser-adjacent workflows for research, documentation and release
verification.

### Planned scope

* [ ] Browser task planning
* [ ] URL inspection mode
* [ ] Docs verification from live pages
* [ ] Release page verification
* [ ] GitHub issue and PR summarization
* [ ] Browser-safe mode
* [ ] Explicit human confirmation before web actions

### Possible commands

```bash
mq-agent browser inspect <url>
mq-agent browser summarize <url>
mq-agent browser verify-release <url>
```

### Non-goals

* No credential handling
* No hidden form submission
* No checkout/payment flows
* No unsafe automation

---

## v0.8.0 — Multi-agent workflows

Goal:

Coordinate specialized local agents for repo audits, release readiness,
documentation, CI diagnosis and semantic memory.

### Planned agents

* [ ] Audit agent
* [ ] Release agent
* [ ] Docs agent
* [ ] CI agent
* [ ] Memory agent
* [ ] Safety agent
* [ ] mqlaunch integration agent
* [ ] mq-mcp tool agent
* [ ] repo-signal intelligence agent

### Possible commands

```bash
mq-agent swarm plan .
mq-agent swarm audit .
mq-agent swarm release-check .
```

### Safety model

Every agent must declare:

* purpose
* allowed tools
* safety class
* approval requirements
* output contract
* failure behavior

---

## v1.0.0 — Stable local agent platform

Goal:

Make mq-agent stable enough to use as the default local agent surface for the mq
ecosystem.

### v1.0.0 requirements

* [ ] Stable CLI command surface
* [ ] Stable config format
* [ ] Stable safety model
* [ ] Stable memory model
* [ ] Stable mqlaunch integration
* [ ] Stable mq-mcp integration
* [ ] Stable repo-signal integration
* [ ] Complete docs
* [ ] Complete examples
* [ ] Complete release checklist
* [ ] Green CI
* [ ] Protected main branch
* [ ] Versioned GitHub release
* [ ] GitHub Pages documentation
* [ ] No known critical safety gaps

---

## Long-term ideas

These are intentionally not scheduled yet.

* Local model fallback
* Ollama integration
* HAL-style conversational shell
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

Work on:

```text
v0.5.1 — semantic memory hardening
```

This should prove that semantic memory is not only implemented, but reliable,
observable and safe in real local use.
