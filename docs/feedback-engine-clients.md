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
mq-agent feedback activation-readiness <candidate-id> --json
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

## v1.31 controlled write boundary

Approval, canary, activation, rollback and state-changing policy commands remain
direct mq-agent operator surfaces. They are not exposed as generic mq-mcp tools
for Codex/Claude. This preserves a single mutation owner and keeps human
approval explicit.

The controlled sequence is:

```text
activation-readiness
  -> approve --approve
  -> canary-run
  -> activate --approve
  -> post-activation-check
  -> rollback --approve (when required)
```

Clients may render the resulting receipts/events/status but must not reimplement
approval expiry, canary validation, effective-policy selection or rollback.

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

The first five are read-only Class A tools. `activation-readiness` is currently a direct mq-agent/mqlaunch read-only surface and is not yet exposed as an MCP tool. `mq_feedback_run` is classified
separately because it consumes bounded compute and writes feedback evidence,
while still having zero production-policy effect.

There is no feedback activation, purge, candidate-state or direct memory
promotion tool exposed to Codex or Claude. Activation readiness does not change that boundary: it reports evidence sufficiency but cannot approve or activate a policy.

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
mqlaunch feedback activation-readiness <candidate-id>
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
