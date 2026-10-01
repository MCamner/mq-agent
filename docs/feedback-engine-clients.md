# Feedback Engine client contract

The Feedback Engine has one policy owner: `mq-agent`.

Clients may expose or render the engine, but they must not reimplement
comparison, verdict, candidate, promotion, or activation policy.

## Authoritative machine interface

For scripts, CI, local tools and adapters, use the JSON surface:

```bash
mq-agent feedback status --json
mq-agent feedback inspect <feedback-run-id> --json
mq-agent feedback compare <feedback-run-id> --json
mq-agent feedback report --task-class repo-review --since 30d --json
mq-agent feedback candidates --json
mq-agent feedback candidate <candidate-id> --json
```

A bounded experiment is an explicit evidence-producing operation:

```bash
mq-agent feedback run \
  --task-class repo-review \
  --repo . \
  --task "review this repository" \
  --json
```

Consumers must treat the JSON result as authoritative. They may format it, but
must not recalculate a verdict from the displayed metrics.

## Storage boundary

Only `mq-agent` writes Feedback Engine runtime evidence.

Other tools must **not** write, edit, rotate, repair or delete
`~/.mq/feedback` directly. They consume mq-agent commands/contracts instead.

This keeps append-only history, schema validation, redaction, locking,
comparison precedence and candidate deduplication in one implementation.

## MCP / Codex / Claude

`mq-mcp` is a thin adapter over mq-agent. The stable MCP surface is:

```text
mq_feedback_status
mq_feedback_inspect
mq_feedback_compare
mq_feedback_report
mq_feedback_candidates
mq_feedback_run
```

The first five are read-only Class A tools. `mq_feedback_run` is classified
separately because it consumes bounded compute and writes feedback evidence,
while still having zero production-policy effect.

There is no feedback activation, purge, candidate-state or direct memory
promotion tool exposed to Codex or Claude in v1.30.

The `feedback-review` skill only selects/explains these tools. It contains no
comparison or promotion policy.

Any MCP-capable coding client, including a client used from VS Code, should
connect to the same mq-mcp server rather than getting a client-specific
Feedback Engine implementation.

## mq-hal

`mq-hal feedback` is a read-only operator view. It renders mq-agent output and
keeps unknown future verdict/reason values neutral instead of mapping them to a
local PASS/WARN/FAIL conclusion.

HAL does not calculate feedback verdicts.

## mqlaunch / macos-scripts

`mqlaunch feedback ...` delegates arguments and exit status to:

```text
mq-agent feedback ...
```

Examples:

```bash
mqlaunch feedback status
mqlaunch feedback report --task-class repo-review --since 30d
mqlaunch feedback inspect <feedback-run-id>
mqlaunch feedback compare <feedback-run-id>
mqlaunch feedback candidates
mqlaunch feedback run --task-class repo-review --repo . --task "review this repository"
```

Shell code owns no feedback state and no comparison policy.

## Ownership summary

```text
Codex / Claude ─┐
mq-hal          ├─> mq-mcp or mq-agent CLI ─> mq-agent Feedback Engine
mqlaunch        ┤                            ├─> ~/.mq/feedback evidence
scripts / CI   ─┘                            └─> mqobsidian review handoff
```

`mqobsidian` remains the durable-memory review/promotion authority. Feedback
candidates do not activate production policy automatically.
