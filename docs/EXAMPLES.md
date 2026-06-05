# Examples

## Audit a repository

Run a read-only audit of the current directory. The planner generates steps, the executor runs them, and the verifier checks each result.

```bash
mq-agent audit .
```

Audit a specific repo:

```bash
mq-agent audit ~/repo-signal
```

With JSON output (suitable for CI or piping):

```bash
mq-agent audit . --json
```

Dry-run (plan only, no tool execution):

```bash
mq-agent audit . --dry-run
```

---

## Plan a goal

Ask the planner to decompose a goal into steps using available tools:

```bash
mq-agent plan "release repo-signal"
```

Output:

```text
PLAN: release repo-signal
1. Run the test suite to confirm no regressions
2. Check git status for uncommitted changes
3. Read pyproject.toml to validate packaging configuration
4. Verify CHANGELOG.md is updated
5. Confirm working tree is clean
```

---

## Show the release plan

```bash
mq-agent release-plan
```

---

## Validate release readiness

Show plan only (suggest mode, default):

```bash
mq-agent release-check
```

Execute checks:

```bash
mq-agent release-check --approve
```

JSON output for CI:

```bash
mq-agent release-check --json
```

---

## Run a command safely

Preview without executing:

```bash
mq-agent run "pytest tests/ -v" --dry-run
```

Execute with approval:

```bash
mq-agent run "pytest tests/ -v" --approve
```

Without `--approve`, the command is shown but not run.

---

## Diagnose CI failures

```bash
mq-agent fix-ci
```

With JSON output:

```bash
mq-agent fix-ci --json
```

---

## Repo summary

```bash
mq-agent repo-summary .
```

```bash
mq-agent repo-summary ~/repo-signal --json
```

---

## Check environment

```bash
mq-agent doctor
```

Checks: `OPENAI_API_KEY`, `git`, `uv`, Python version, and mq-mcp availability.
When mq-mcp is running, doctor also checks whether
`validate_orchestration_contract` is available.

---

## Review via mq-mcp

Review commands route through mq-mcp and pass findings through unchanged:

```bash
mq-agent review file README.md
mq-agent review diff
mq-agent review repo .
```

Forward review modes to mq-mcp:

```bash
mq-agent review file mq_agent/main.py --security
mq-agent review repo . --architecture
mq-agent review diff --json
```

Risk review is used only when the installed mq-mcp exposes the matching
`risk_review_*` tool:

```bash
mq-agent review diff --risk
```

Preview what would be called without contacting mq-mcp:

```bash
mq-agent review file mq_agent/main.py --dry-run
mq-agent review diff --dry-run --security
mq-agent review repo . --dry-run --architecture --risk
```

Prefer fast Class A tools (mq-mcp routes internally):

```bash
mq-agent review file mq_agent/main.py --fast
mq-agent review diff --fast --security
```

Architecture context is shown automatically after review findings when
`list_architecture_decisions` is available in mq-mcp.

---

## Learned review patterns

Check learn system availability:

```bash
mq-agent learn status
mq-agent learn status --json
```

Search learned patterns:

```bash
mq-agent learn search "state mutation"
mq-agent learn search "guard clauses" --json
```

Fetch a pattern explanation:

```bash
mq-agent learn explain p-42
mq-agent learn explain p-42 --json
```

mq-agent does not implement severity scoring, architecture reasoning, risk
classification, semantic retrieval, review heuristics or drift detection.
It also does not extract or store learned patterns locally. Optional Ollama-backed
learn extraction belongs in mq-mcp; mq-agent only surfaces read-only learn
status, search and explain results.

---

## List registered tools

```bash
mq-agent tools
```

---

## Launch the TUI

```bash
mq-agent tui
```

Keyboard bindings:

- `enter` — run selected command
- `c` — clear log
- `q` — quit

---

---

## Score a repo (no API key required)

Quick README score and publish checklist — no AI, instant result:

```bash
mq-agent score .
```

JSON output:

```bash
mq-agent score . --json
```

---

## Full repo-signal assessment

Scan + README score + publish checklist + AI improvement plan:

```bash
mq-agent signal .
```

Dry-run (no AI call):

```bash
mq-agent signal . --dry-run
```

---

## Declarative task workflows

List available YAML task workflows:

```bash
mq-agent task list
mq-agent task list --json
```

Preview a task without executing:

```bash
mq-agent task run repo-audit --dry-run
mq-agent task run suggest-patches --dry-run --json
```

Run a task (executes all steps via the tool registry):

```bash
mq-agent task run repo-audit
mq-agent task run suggest-patches
```

---

## Browser-assisted verification

Inspect a URL (title, description, headings, links, word count):

```bash
mq-agent browser inspect https://github.com/MCamner/mq-agent
```

Plain-text summary:

```bash
mq-agent browser summarize https://github.com/MCamner/mq-agent
```

Verify a GitHub release page:

```bash
mq-agent browser verify-release https://github.com/MCamner/mq-agent/releases/tag/v0.9.0
mq-agent browser verify-release https://github.com/MCamner/mq-agent/releases/tag/v0.9.0 --tag v0.9.0
```

---

## Controlled specialist orchestration

List available swarm configurations:

```bash
mq-agent swarm list
```

Dry-plan a swarm config (no API key, no execution):

```bash
mq-agent swarm plan audit
mq-agent swarm plan audit --json
```

Run the audit swarm (read-only, no `--approve` needed):

```bash
mq-agent swarm run audit .
```

Run the release-check swarm (requires `--approve` for write agents):

```bash
mq-agent swarm release-check .
mq-agent swarm release-check . --approve
```

---

## Semantic repository memory

Check memory status:

```bash
mq-agent memory status
mq-agent memory status --json
```

Preview what would be uploaded (dry-run, default):

```bash
mq-agent memory build
```

Upload to vector store (requires explicit approval):

```bash
mq-agent memory refresh --approve
```

Diagnose the memory environment:

```bash
mq-agent memory doctor
mq-agent memory doctor --json
```

Search mq-mcp semantic memory (requires mq-mcp v1.4.0+):

```bash
mq-agent memory search "architecture decisions"
mq-agent memory search "safety gates" --json
```

Store an item in mq-mcp semantic memory (Class C write — requires `--approve`):

```bash
mq-agent memory store "arch-key" "Use MCPBridge for all tool routing." --approve
mq-agent memory store "arch-key" "value" --dry-run
```

---

## Skill discovery

Discover and normalize the repo-local `SKILLS.md` index without executing skills:

```bash
mq-agent skill list .
mq-agent skill list . --json
```

The JSON output uses the `mq.skill_index.v1` contract with normalized
`mq.skill.v1` records.

Preview which skill would handle a request:

```bash
mq-agent skill route "check release readiness"
mq-agent skill route "audit this repo" --json
```

The route preview uses `mq.skill_route.v1` and never executes the selected
command.

Summarize skill indexes across MQ ecosystem repos:

```bash
mq-agent skill ecosystem
mq-agent skill ecosystem ../mq-agent ../mq-mcp --json
```

The ecosystem summary uses `mq.ecosystem_skills.v1` and reports missing
`SKILLS.md` files without failing.

Preview approval-gated execution for a routed skill:

```bash
mq-agent skill run "list skills" --json
mq-agent skill run "list skills" --approve
```

`skill run` only executes supported existing `mq-agent` command surfaces and
refuses unsupported commands or missing approvals.

---

## MCP server management

Start the local mq-mcp tool server:

```bash
mq-agent mcp start
```

Check status and tool counts:

```bash
mq-agent mcp status
mq-agent mcp status --json
```

List available MCP tools with safety classes:

```bash
mq-agent mcp tools
```

Stop the server:

```bash
mq-agent mcp stop
```

Register an external MCP server:

```bash
mq-agent mcp connect MyServer http://localhost:9000
mq-agent mcp disconnect MyServer
```

---

## See demo output

Sample output files are in [`docs/demo/`](demo/).
