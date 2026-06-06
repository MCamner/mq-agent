# Skills

mq-agent ships with built-in skills for structured AI agent workflows and mq
ecosystem integrations.

Skills live in `skills/`. Most map directly to CLI commands and agent classes;
integration skills document how mq-agent should route work to neighboring mq
tools.

## Built-in skills

### repo-audit

Read-only repository audit using the Planner→Executor→Verifier loop.

```text
skills/repo-audit/SKILL.md
```

Command: `mq-agent audit .`
Outputs: summary, steps, verification

### release-readiness

Full release validation: git state, tests, version, changelog, CI.

```text
skills/release-readiness/SKILL.md
```

Command: `mq-agent release-check`
Outputs: summary, checks, next_actions

### signal-assessment

repo-signal static scan + AI improvement plan with scored output.

```text
skills/signal-assessment/SKILL.md
```

Command: `mq-agent signal .`
Outputs: scores, readme, publish_checklist, focus_areas, next_actions

### ci-diagnosis

Diagnose CI failures and generate actionable fix steps.

```text
skills/ci-diagnosis/SKILL.md
```

Command: `mq-agent fix-ci`
Outputs: ci_context, steps, recommended_fixes

### visual-analysis

Analyze images, screenshots and visual diffs through `mq-image-analyze`.

```text
skills/visual-analysis/SKILL.md
```

Command: `mq-image analyze`, `mq-image analyze-ui`, `mq-image compare`
Outputs: visual_summary, ocr_text, detected_regions, risk_signals, confidence

### mq-mcp-review-orchestration

Route review, risk, security and architecture workflows through mq-mcp without
duplicating cognition logic in mq-agent.

```text
skills/mq-mcp-review-orchestration/SKILL.md
```

Command: future `mq-agent review` / task-runner backed review workflows
Outputs: findings, severity_summary, next_actions, raw_mcp_result

## Safety modes

All skills respect the safety gate:

| Mode      | Behaviour                          |
|-----------|------------------------------------|
| read-only | Only read tools allowed            |
| suggest   | Plan shown, nothing executed       |
| execute   | Runs after safety check            |
| dangerous | No restrictions                    |

## Run a skill

```bash
mq-agent audit .              # repo-audit
mq-agent signal .             # signal-assessment
mq-agent release-check        # release-readiness
mq-agent fix-ci               # ci-diagnosis
# future: mq-agent review .   # mq-mcp-review-orchestration
```

All commands support `--dry-run` and `--json`.
