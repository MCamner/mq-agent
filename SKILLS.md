# Skills

mq-agent ships with built-in skills for structured AI agent workflows.

Skills live in `skills/` and map directly to CLI commands and agent classes.

## Built-in skills

### repo-audit

Read-only repository audit using the Planner→Executor→Verifier loop.

```text
skills/repo-audit/SKILL.md
```

Command: `mq-agent audit .`

### release-readiness

Full release validation: git state, tests, version, changelog, CI.

```text
skills/release-readiness/SKILL.md
```

Command: `mq-agent release-check`

### signal-assessment

repo-signal static scan + AI improvement plan with scored output.

```text
skills/signal-assessment/SKILL.md
```

Command: `mq-agent signal .`

### ci-diagnosis

Diagnose CI failures and generate actionable fix steps.

```text
skills/ci-diagnosis/SKILL.md
```

Command: `mq-agent fix-ci`

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
```

All commands support `--dry-run` and `--json`.
