# Command Surface

This file is the canonical command-count reference for `mq-agent` v1.0.0.
README, release notes, GitHub Pages and integration docs should link here
instead of redefining command counts in prose.

## System Layers

```text
mqlaunch -> mq-agent -> mq-mcp / mq-hal / repo-signal
```

| Layer | Role |
|---|---|
| `mqlaunch` | Human terminal entrypoint — menus and shortcuts only |
| `mq-agent` | Orchestration: planning, safety gates, tool routing, verification |
| `mq-mcp` | Execution runtime: review engine, architecture memory, 66 MCP tools |
| `repo-signal` | Repository intelligence: quality, publish-readiness, symbol exports |
| `mq-hal` | Observability: runtime health, model health, status summaries |

`mq-agent mcp *` commands must respect mq-mcp safety classes (A/B/C/D) and
profiles. Class C/D tools always require explicit `--approve`. mq-agent must
not reimplement mq-mcp review logic or architecture reasoning locally.

## Flag Contract

These rules hold across the whole command surface and are enforced by
`tests/test_flag_contract.py`:

* `--dry-run` never writes — it previews the calls and returns before any
  execution, including `--brain` writes.
* `--json` is machine-readable: stdout is parseable JSON.
* `--brain` is the explicit opt-in for a brain write on otherwise read-only
  commands, and always respects `--dry-run`. Every `--brain` command also
  offers `--dry-run` and `--json`.
* `--approve` is required for commands whose primary action is a write
  (`learn store/promote/from-review/from-diff`, `brain record-review`,
  `decide`).

## mq-agent Commands

| Command | Safety mode | Needs API key | Notes |
|---|---|---:|---|
| `mq-agent doctor` | read-only | no | Environment check |
| `mq-agent score .` | read-only | no | README score and publish checklist |
| `mq-agent repo-summary .` | read-only | no | Concise repository overview |
| `mq-agent tools` | read-only | no | List registered tools |
| `mq-agent tools --describe <name>` | read-only | no | Tool metadata and safety class |
| `mq-agent tools --mcp` | read-only | no | Include discovered MCP tools |
| `mq-agent audit .` | read-only | yes | AI-assisted repo audit |
| `mq-agent docs-audit .` | read-only | yes | Audit README, CHANGELOG, docstrings and /docs |
| `mq-agent signal .` | read-only | yes | repo-signal plus AI improvement plan |
| `mq-agent plan "goal"` | suggest | yes | Generate an execution plan |
| `mq-agent release-plan` | suggest | yes | Show the standard release plan |
| `mq-agent release-check` | suggest | yes | Validate release readiness |
| `mq-agent release-check --approve` | execute | yes | Execute release checks |
| `mq-agent fix-ci` | suggest | yes | Diagnose CI failures |
| `mq-agent run "cmd" --approve` | execute | no | Safe shell command execution |
| `mq-agent run --stack` | read-only | no | Canonical stack runtime pipeline |
| `mq-agent tui` | read-only | no | Textual dashboard |

## Review Commands

Review commands are orchestration-only. mq-agent calls mq-mcp review tools and
renders the returned findings without changing severity labels or implementing
local review heuristics.

| Command | Needs mq-mcp | Notes |
|---|---:|---|
| `mq-agent review file <path>` | yes | Calls mq-mcp `review_file` |
| `mq-agent review file <path> --json` | yes | Raw mq-mcp JSON result |
| `mq-agent review diff` | yes | Calls mq-mcp `review_diff` |
| `mq-agent review repo [path]` | yes | Calls mq-mcp `review_repo` |
| `mq-agent review * --security` | yes | Passes `security=true` to mq-mcp |
| `mq-agent review * --architecture` | yes | Passes `architecture=true` to mq-mcp |
| `mq-agent review * --architecture-image <path>` | mq-image-analyze + mq-mcp | Observes image, then passes visual context to architecture review |
| `mq-agent review * --visual <path>` | mq-image-analyze + mq-mcp | Alias for `--architecture-image` |
| `mq-agent review * --risk` | yes | Requires installed mq-mcp `risk_review_*` tools |
| `mq-agent review * --fast` | yes | Prefer Class A tools; mq-mcp handles routing |
| `mq-agent review * --dry-run` | no | Show what would be called, no execution |
| `mq-agent learn status` | yes | Check mq-mcp learn system availability |
| `mq-agent learn search <query>` | yes | Search mq-mcp learned review patterns |
| `mq-agent learn explain <pattern-id>` | yes | Fetch pattern explanation from mq-mcp |

## Memory Commands

mqobsidian memory engine commands are local and read-only. They do not require
OpenAI, Ollama or mq-mcp.

| Command | Needs vector store | Notes |
|---|---:|---|
| `mq-agent memory ingest` | no | Scan mqobsidian Markdown notes into a local index |
| `mq-agent memory ingest --json` | no | Machine-readable mqobsidian memory index |
| `mq-agent memory query <query>` | no | Search mqobsidian memory notes |
| `mq-agent memory search-vault <query>` | no | Alias for mqobsidian memory search |
| `mq-agent memory summarize` | no | Summarize mqobsidian memory by section |
| `mq-agent memory link` | no | Report read-only link candidates between notes |
| `mq-agent memory status` | no | Reports vector store ID and repo-signal availability |
| `mq-agent memory status --json` | no | Machine-readable status output |
| `mq-agent memory doctor` | no | Diagnose environment with actionable fixes |
| `mq-agent memory doctor --json` | no | Machine-readable diagnostics |
| `mq-agent memory build .` | no | Dry-run preview of semantic upload (safe default) |
| `mq-agent memory build . --no-dry-run` | yes | Upload semantic memory |
| `mq-agent memory refresh . --approve` | yes | Upload with explicit approval gate |
| `mq-agent memory search <query>` | yes | Search mq-mcp semantic memory (requires mq-mcp v1.4.0+) |
| `mq-agent memory search <query> --json` | yes | Raw mq-mcp JSON result |
| `mq-agent memory store <key> <value> --approve` | yes | Store item in mq-mcp semantic memory (Class C write) |
| `mq-agent memory store <key> <value> --dry-run` | no | Preview without writing |
| `mq-agent context export --repo <repo> --output-root <dir>` | no | Export compact `.mq/context/` snapshot from mqobsidian context cards |

## Obsidian Inbox Commands

The promotion inbox surface `mqlaunch` delegates to. Reads come from mqobsidian's
canonical exports through the single entrypoint
`exports/truth-export-index.json`; there is no raw-vault fallback. Reads fail
closed on a stale, missing, or drifted truth surface rather than reporting
whatever is on disk.

Ranking is mq-agent's computation over mqobsidian's policy: the weights and
thresholds are vault data, the formula and routing are code here. `--json` emits
`inbox_promotion_orchestration.v1` and nothing else, including on failure, so a
caller that pipes it can tell a contract error from a crash.

The five transition verbs are explicit — never a generic mqobsidian passthrough.
Every one previews by default and writes only with `--confirm`.
`auto-promotable` means eligible for approval, never an unattended write.

| Command | Writes | Needs `--confirm` | Notes |
|---|---:|---:|---|
| `mq-agent obsidian inbox list` | no | no | Promotion candidates from the canonical inbox export |
| `mq-agent obsidian inbox read <id>` | no | no | One candidate; exits 1 when not in the inbox |
| `mq-agent obsidian inbox rank` | no | no | Policy-weighted ranking and bucket routing |
| `mq-agent obsidian inbox <cmd> --json` | no | no | `inbox-candidate-list.v1` / `inbox-candidate-read.v1` / `inbox_promotion_orchestration.v1` |
| `mq-agent obsidian promote <id> --reason R --evidence REF` | via mqobsidian | yes | candidate → promoted; requires traceable published evidence |
| `mq-agent obsidian reject <id> --reason R` | via mqobsidian | yes | candidate → archived; no durable learn record |
| `mq-agent obsidian defer <id> --reason R` | via mqobsidian | yes | candidate → observed; no durable learn record |
| `mq-agent obsidian rollback <id> --reason R` | via mqobsidian | yes | promoted → candidate; removes the generated learn projection |
| `mq-agent obsidian deprecate <id> --reason R` | via mqobsidian | yes | promoted → deprecated; retains the record |

Writes are delegated: mq-agent passes the operator's intent — id, reason, and
validated evidence refs — to mqobsidian's own CLI, which owns the state machine,
the write-ahead journal, and the promotion event. mq-agent never writes memory.

## Model Commands

Ollama model runtime commands. Config writes go to `~/.mq-agent/models.json`
and require `--approve`.

| Command | Writes | Notes |
|---|---:|---|
| `mq-agent models list` | no | List local Ollama models |
| `mq-agent models list --json` | no | Machine-readable Ollama inventory |
| `mq-agent models current` | no | Show active profile, model and config path |
| `mq-agent models current --json` | no | Machine-readable active model state |
| `mq-agent models doctor` | no | Validate Ollama runtime, profiles, mq-learn drift and JSON output |
| `mq-agent models doctor --json` | no | Machine-readable `ollama_runtime_doctor.v1` verdict |
| `mq-agent models doctor --no-smoke` | no | Skip model generation while retaining runtime checks |
| `mq-agent models switch <profile>` | no | Dry-run profile switch preview |
| `mq-agent models switch <model> --profile <profile>` | no | Dry-run profile assignment preview |
| `mq-agent models switch <model> --profile <profile> --approve` | yes | Write model profile config |
| `mq-agent models bench [model]` | no | Measure duration, token counts, tokens/sec and JSON/schema validity |
| `mq-agent models bench [model] --json` | no | Machine-readable `ollama_model_benchmark.v1` result |
| `mq-agent models bench [model] --keep-alive <value>` | no | Override the default `keep_alive=0` for the request |

## Brain Commands

Direct mqobsidian vault commands. All writes are Class C and require `--approve`.

| Command | Writes | Notes |
|---|---:|---|
| `mq-agent brain structure` | no | Check the vault against the standard export structure (exit 1 if incomplete) |
| `mq-agent brain structure --json` | no | Machine-readable structure report |
| `mq-agent brain structure --init --approve` | yes | Create missing standard directories, each with a README |
| `mq-agent brain record-review --source <id> --approve` | yes | Write a review summary via mq-mcp `brain_record_review` |
| `mq-agent decide <title> --context ... --decision ... --rationale ... --approve` | yes | Write an ADR via mq-mcp `brain_record_decision` |

The standard export structure (see [VAULT_STRUCTURE.md](VAULT_STRUCTURE.md)):
`memory/stack-truth/`, `memory/reviews/`, `memory/learn/`, `mq-stack/runs/`,
`mq-stack/roadmaps/`.

## MCP Commands

| Command | Needs MCP server | Notes |
|---|---:|---|
| `mq-agent mcp status` | no | Reachability, tool counts, contract freshness, semantic memory count |
| `mq-agent mcp tools` | no | List MCP tools with safety classes |
| `mq-agent run-tool <name>` | yes | Execute a local MCP tool through safety gates |
| `mq-agent run-tool <name> --dry-run` | no | Preview without contacting mq-mcp |
| `mq-agent run-tool <name> --arg k=v` | yes | Pass tool arguments |
| `mq-agent run-tool <name> --approve` | yes | Allow write-capable or subprocess tools |
| `mq-agent run-tool <name> --dangerous` | yes | Allow dangerous delete/remove class tools |
| `mq-agent run-tool observe_architecture --arg image_path=...` | mq-image-analyze | Visual architecture observation context |
| `mq-agent run-tool image_ocr --arg image_path=...` | mq-image-analyze | OCR context from image-derived text |

## Browser Commands

All browser commands are read-only (GET requests only). No credentials, no form submission.

| Command | Needs network | Notes |
|---|---:|---|
| `mq-agent browser inspect <url>` | yes | Structured URL metadata: title, h1/h2, links, word count |
| `mq-agent browser inspect <url> --json` | yes | Machine-readable metadata |
| `mq-agent browser summarize <url>` | yes | Plain-text content summary |
| `mq-agent browser summarize <url> --json` | yes | Machine-readable summary |
| `mq-agent browser verify-release <url>` | yes | Verify release page fields |
| `mq-agent browser verify-release <url> --tag v0.7.0` | yes | Also check expected version tag |
| `mq-agent browser verify-release <url> --json` | yes | Machine-readable verification result |

## Task Commands

| Command | Notes |
|---|---|
| `mq-agent task list` | List available YAML task workflow files |
| `mq-agent task list --json` | Machine-readable task list |
| `mq-agent task run <name>` | Execute a declarative YAML workflow |
| `mq-agent task run <name> --dry-run` | Preview steps without execution |
| `mq-agent task run <name> --json` | Machine-readable step results |

## Swarm Commands

Each swarm runs multiple agents in sequence with declared safety contracts.

| Command | Needs API key | Notes |
|---|---:|---|
| `mq-agent swarm list` | no | List swarm configs with agents and safety classes |
| `mq-agent swarm list --json` | no | Machine-readable |
| `mq-agent swarm plan <config>` | no | Show agents that would run — no execution |
| `mq-agent swarm plan <config> --json` | no | Machine-readable plan |
| `mq-agent swarm run <config> [path]` | yes | Execute swarm, unified report |
| `mq-agent swarm run <config> [path] --dry-run` | no | Preview without execution |
| `mq-agent swarm run <config> [path] --approve` | yes | Allow write-capable agents |
| `mq-agent swarm run <config> [path] --json` | yes | Machine-readable results |
| `mq-agent swarm audit [path]` | yes | Shorthand: audit + signal + docs |
| `mq-agent swarm audit [path] --dry-run` | no | Preview |
| `mq-agent swarm release-check [path]` | yes | Shorthand: CI + audit + release |
| `mq-agent swarm release-check [path] --approve` | yes | Enable release agent |

### Built-in swarm configs

| Config | Agents | Approve needed? |
|---|---|---|
| `audit` | audit + signal + docs | no |
| `release-check` | ci + audit + release | yes (for release agent) |
| `ci` | ci + audit | no |

## Stack Commands

Stack commands operate across all mq-stack repos without an API key. They read
local clones and git history only. No AI calls unless `--brain` or `--decide` is used.

### Stack status and sweep

| Command | Needs API key | Notes |
|---|---:|---|
| `mq-agent stack status` | no | Version, branch, drift risk and readiness per repo |
| `mq-agent stack status --json` | no | Machine-readable status |
| `mq-agent stack truth-export` | no | Write stack truth note (contract + release gates) to mqobsidian |
| `mq-agent stack truth-export --json` | no | Machine-readable truth export result |
| `mq-agent stack export` | no | Alias for `stack truth-export` |
| `mq-agent stack sweep` | yes (signal) | Run repo-signal over all repos |
| `mq-agent stack sweep --dry-run` | no | Preview repos that would be scanned |
| `mq-agent stack sweep --json` | yes | Machine-readable sweep results |
| `mq-agent stack sweep --brain` | yes | Write brain note per repo via mqobsidian |
| `mq-agent stack sweep --decide` | yes | Write ADR snapshot to brain |
| `mq-agent stack sweep --alert` | yes | Exit 1 if any repo dropped or is below 80 |
| `mq-agent stack sweep --alert --threshold N` | yes | Custom drop threshold |

### Stack health history

| Command | Notes |
|---|---|
| `mq-agent stack history` | Show last 5 sweep scores per repo |
| `mq-agent stack history -n N` | Show last N sweeps |
| `mq-agent stack history --diff` | Score delta between two most recent sweeps |
| `mq-agent stack history --json` | Machine-readable history |

Approved `mq-agent stack loop --execute --approve` attempts are also appended
to `$MQ_AGENT_STATE_DIR/stack-loop-history.jsonl` (default `~/.mq-agent`). The
loop-audit file is write-free for dry-run, preview, idle and unapproved modes.

### Stack alert

Exits 0 when no alerts, exits 1 when alerts are found — CI-friendly.

| Command | Notes |
|---|---|
| `mq-agent stack alert` | Warn when any repo dropped ≥ 10 pts or is below 80 |
| `mq-agent stack alert --threshold N` | Custom drop threshold |
| `mq-agent stack alert --min-score N` | Custom minimum score |
| `mq-agent stack alert --json` | Machine-readable alert output |

### Stack report and release gate

| Command | Notes |
|---|---|
| `mq-agent stack report` | Score, trend, alert, readiness in one table |
| `mq-agent stack report --json` | Machine-readable report |
| `mq-agent stack release-check` | Release-readiness check; exits 1 on blocker |
| `mq-agent stack release-check --dry-run` | Preview repos that would be checked |
| `mq-agent stack release-check --json` | Machine-readable; exits 1 on NO-GO |
| `mq-agent stack release-check --ci` | CI mode; skips repos missing from the workspace |
| `mq-agent stack release-notes` | Draft release notes from git log since last tag |
| `mq-agent stack release-notes --repo <name>` | Limit to one repo |
| `mq-agent stack release-notes --json` | Machine-readable notes |

### Stack contract gate

Validates that every repo has a `.mq/repo-contract.json` in sync with `VERSION`.
Exits 0 only when all repos are READY or REVIEW. Exits 1 on BLOCKED or DRIFT.

| Command | Notes |
|---|---|
| `mq-agent stack contract-check` | Validate contract manifests across all repos |
| `mq-agent stack contract-check --json` | Machine-readable; exits 1 on NOT READY |
| `mq-agent stack contract-check --ci` | CI mode; missing repos SKIPPED instead of BLOCKED |

Status levels: `READY` → `REVIEW` (uncommitted changes) → `DRIFT` (version mismatch) → `BLOCKED` (missing file/field).
In CI mode only: `SKIPPED` (repo not present in the CI workspace; never fails the gate).

| Command | Notes |
|---|---|
| `mq-agent stack skills-check` | Run each repo's `scripts/check-skills.sh` (frontmatter, cross-refs, paths, SKILLS.md sync) |
| `mq-agent stack skills-check --json` | Machine-readable; exits 1 on NOT READY |
| `mq-agent stack skills-check --ci` | CI mode; missing repos SKIPPED instead of BLOCKED |

Status levels: `READY` (check passed) → `REVIEW` (skills present without a `check-skills.sh` validator) → `DRIFT` (check-skills.sh failed) → `BLOCKED` (repo or checker unavailable). Only `DRIFT` and `BLOCKED` fail the gate; `REVIEW` and `SKIPPED` do not.

Both gates run automatically in `.github/workflows/mq-stack-gate.yml` on every
pull request and push to `main`.

### Stack release

Orchestrated single-repo release pipeline. Dry-run by default; exits 1 on
NO-GO or any failed step. See `docs/STACK_RELEASE.md`.

| Command | Notes |
|---|---|
| `mq-agent stack release --repo <name>` | Dry-run: show the release plan |
| `mq-agent stack release --repo <name> --execute` | Apply the release (bump, changelog, tag, push, truth-export) |
| `mq-agent stack release --repo <name> --bump minor` | Version bump: patch (default), minor or major |
| `mq-agent stack release --repo <name> --version X.Y.Z` | Explicit target version |
| `mq-agent stack release --repo <name> --json` | Machine-readable plan or result |
| `mq-agent stack release --all` | Dry-run: plan every stack repo at once (ready / blocked / up-to-date); exits 1 if any repo is blocked |
| `mq-agent stack release --all --json` | Machine-readable multi-repo plan (`mq_stack_release_all.v1`) |

`--all` is dry-run only: it surveys the whole stack and reports which repos are
ready to release, which are blocked (and why), and which are up-to-date. It does
not apply anything — release each ready repo with `--repo <name> --execute`, so
every write stays a single, explicit, per-repo step.

### Stack cockpit

One merged read-only view of the whole stack — later the input to mq-hal.

| Command | Notes |
|---|---|
| `mq-agent stack cockpit` | Repo, version, branch, dirty, contract, gate, next action per repo |
| `mq-agent stack cockpit --json` | Machine-readable cockpit snapshot |

### Stack runtime

One runtime pass across repo-signal, mq-mcp, Ollama, brain export rendering and
release readiness. Read-only by default; `--brain` writes the truth export only
when paired with `--approve`.

| Command | Notes |
|---|---|
| `mq-agent stack run` | Run the stack runtime gate |
| `mq-agent run --stack` | Canonical root alias for `stack run` |
| `mq-agent stack run --dry-run` | Run without write steps |
| `mq-agent stack run --json` | Machine-readable runtime result; exits 1 on FAIL |
| `mq-agent stack run --markdown` | Markdown runtime report with pipeline and checks |
| `mq-agent stack run --brain --approve` | Write the stack truth export after runtime checks |
| `mq-agent stack run --ci` | CI mode for release gates; skips missing sibling repos |

### Brain release gate

Pre-release checklist for the brain-integrated stack. Read-only; exit 1 on
NO-GO. See `docs/BRAIN_GATE.md`.

| Command | Notes |
|---|---|
| `mq-agent stack brain-gate` | contract-check + release-check + truth-export dry-run + vault structure + brain write path |
| `mq-agent stack brain-gate --json` | Machine-readable gate result |

## mqlaunch Agent Menu

The mqlaunch agent menu has exactly 19 items.

| Menu item | Runs |
|---:|---|
| 1 | `mq-agent score .` |
| 2 | `mq-agent signal .` |
| 3 | `mq-agent repo-summary .` |
| 4 | `mq-agent tools` |
| 5 | `mq-agent audit .` |
| 6 | `mq-agent signal .` |
| 7 | `mq-agent release-check` |
| 8 | `mq-agent fix-ci` |
| 9 | `mq-agent doctor` |
| 10 | `mq-agent tui` |
| 11 | `mq-agent mcp status` |
| 12 | `mq-agent mcp tools` |
| 13 | start mq-mcp server |
| 14 | stop mq-mcp server |
| 15 | `mq-agent review repo . --brain` |
| 16 | promote learn pattern to mqobsidian |
| 17 | demo flow |
| 18 | `mq-agent stack sweep --brain` |
| 19 | `mq-agent stack loop` |

## mqlaunch Direct Command Surface

`mqlaunch agent ...` exposes 6 direct subcommands plus the menu entrypoint.

| mqlaunch command | Runs |
|---|---|
| `mqlaunch agent` | Opens the mq-agent menu |
| `mqlaunch agent doctor` | `mq-agent doctor` |
| `mqlaunch agent score .` | `mq-agent score .` |
| `mqlaunch agent audit .` | `mq-agent audit .` |
| `mqlaunch agent release-check --dry-run` | `mq-agent release-check --dry-run` |
| `mqlaunch agent mcp-status` | `mq-agent mcp status` |
| `mqlaunch agent mcp-tools` | `mq-agent mcp tools` |

## mqlaunch Direct Prompt Commands

The mqlaunch top-level prompt exposes exactly 6 direct prompt commands.

| Prompt input | Runs |
|---|---|
| `agent score` | `mq-agent score .` |
| `agent audit` | `mq-agent audit .` |
| `agent doctor` | `mq-agent doctor` |
| `agent release-check` | `mq-agent release-check` |
| `agent mcp-status` | `mq-agent mcp status` |
| `agent mcp-tools` | `mq-agent mcp tools` |

## Smoke-Test Coverage

`scripts/smoke-mqlaunch.sh` verifies the `mqlaunch agent ...` bridge without
a live interactive session or OpenAI API call.

| Smoke check | Command path |
|---|---|
| doctor | `mqlaunch agent doctor` |
| score | `mqlaunch agent score .` |
| repo-summary | `mqlaunch agent repo-summary .` |
| mcp-status | `mqlaunch agent mcp-status` |

`release-check` is excluded from the smoke suite — it calls the AI planner and
requires `OPENAI_API_KEY`. `mq-mcp` does not need to be running for the
`mcp-status` smoke check; the command reports reachability cleanly.
