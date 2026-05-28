# Examples

Runnable mq-agent examples and sample outputs.

The canonical walkthrough lives in [`docs/EXAMPLES.md`](../docs/EXAMPLES.md).
This folder is a quick entrypoint for people and tools that look for a top-level
`examples/` directory.

## Quick Flows

### Score a repository

```bash
mq-agent score .
mq-agent score . --json
```

No API key required.

### Dry-run a repository audit

```bash
mq-agent audit . --dry-run
mq-agent task run repo-audit --dry-run
```

### Validate release readiness

```bash
mq-agent release-check --dry-run
mq-agent release-check --json
```

### Inspect mq-mcp tools

```bash
mq-agent mcp status
mq-agent mcp tools
mq-agent run-tool read_repo_file --arg path=README.md --dry-run
```

### Check semantic memory state

```bash
mq-agent memory status
mq-agent memory doctor
mq-agent memory build .
```

Memory upload is dry-run by default unless explicitly approved.

## Sample Outputs

Existing sample outputs are stored under [`docs/demo/`](../docs/demo/):

- [`audit-output.json`](../docs/demo/audit-output.json)
- [`release-check.json`](../docs/demo/release-check.json)
- [`repo-summary.txt`](../docs/demo/repo-summary.txt)
- [`fix-ci.txt`](../docs/demo/fix-ci.txt)

## Task Examples

Declarative workflows live under [`tasks/`](../tasks/):

- [`audit.yaml`](../tasks/audit.yaml)
- [`release.yaml`](../tasks/release.yaml)
- [`fix_ci.yaml`](../tasks/fix_ci.yaml)
- [`suggest.yaml`](../tasks/suggest.yaml)
- [`browser_verify.yaml`](../tasks/browser_verify.yaml)
- [`swarm_audit.yaml`](../tasks/swarm_audit.yaml)
