# MQ Release Operator

MQ Release Operator is the terminal-first release and review flow for mq-agent.

The core command is:

```bash
mq-agent release status --repo . --target v1.4.0
```

It asks mq-mcp to run Release Gate v2 and renders the result for a human
operator:

```text
PASS / WARNING / BLOCKED
Blockers
Warnings
Next actions
```

## Responsibility Boundary

```text
mq-agent owns commands, orchestration, routing and operator output.
mq-mcp owns Release Gate v2 rules, blocker/warning logic and JSON output.
repo-signal owns repo readiness and metadata exports.
mq-image-analyze owns OCR, screenshot analysis, diagram analysis and perception output.
mq-hal owns runtime health and safe operator command routing.
```

mq-agent must not duplicate Release Gate v2 rules. It asks mq-mcp for release
status and renders the response.

## Commands

```bash
mq-agent release status
mq-agent release gate
mq-agent release explain
mq-agent dashboard --json
mq-agent review perception screenshot.png
```

`mq-agent dashboard` shows lightweight stack health across mq-agent, mq-mcp,
repo-signal, mq-image-analyze and mq-hal.

## mqlaunch Review Tools

The mqlaunch entrypoints used for release-operator verification are:

```bash
mqlaunch agent mcp-status
mqlaunch agent mcp-tools
mqlaunch agent release-check
mqlaunch agent review release
mqlaunch agent release-workflow
```

Current known gate gap:

```text
mqlaunch agent review release
  -> mq-agent review release
  -> mq-agent release status
  -> mq-mcp release_gate_run
  -> BLOCKED when mq-agent lacks release/tool contract schema inputs
```

This is expected until `mq-agent` has the release/tool contract schema expected
by Release Gate v2. It means the mqlaunch route works and the gate is reporting
a real missing contract input; it is not a perception-routing failure.

## Release Flow

```text
mq-agent release status
        ↓
mq-agent asks mq-mcp
        ↓
mq-mcp runs Release Gate v2
        ↓
mq-agent renders operator output
```

## Perception Flow

```text
screenshot.png
    ↓
mq-image-analyze
    ↓
perception JSON
    ↓
mq-agent review context
    ↓
mq-mcp contract/review check
```
