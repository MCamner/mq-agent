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

```
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

## See demo output

Sample output files are in [`docs/demo/`](demo/).
