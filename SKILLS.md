# Skills

mq-agent ships with built-in skills for structured AI agent workflows and mq
ecosystem integrations.

Skills live in `skills/`. Most map directly to CLI commands and agent classes;
integration skills document how mq-agent should route work to neighboring mq
tools.

The table below is generated from SKILL.md frontmatter by
`./scripts/check-skills.sh --fix`. Do not edit it by hand.

## Built-in skills

<!-- BEGIN GENERATED SKILLS TABLE -->
| Skill | Description |
| ----- | ----------- |
| [ci-diagnosis](skills/ci-diagnosis/SKILL.md) | Use when CI is failing. Diagnoses test, lint, and type check failures and generates fix steps. |
| [mq-mcp-review-orchestration](skills/mq-mcp-review-orchestration/SKILL.md) | Use when adding or changing mq-agent workflows that route review, risk, security, architecture, or repo-aware cognition work through mq-mcp. |
| [release-readiness](skills/release-readiness/SKILL.md) | Use when preparing an mq-agent release. Validates git state, version alignment, changelog, tests, CI, the stack contract gate, and release-notes draft. |
| [repo-audit](skills/repo-audit/SKILL.md) | Use when auditing a repository for code quality, git state, structure, and test coverage. Read-only, safe to run anywhere. |
| [repo-aware](skills/repo-aware/SKILL.md) | Use when inspecting, explaining, planning, reviewing, or changing an existing repository. Combine local files, repo signals, conventions, Git state, docs, tests, release flow, and AI-readiness evidence before acting. |
| [signal-assessment](skills/signal-assessment/SKILL.md) | Use when scoring a repository's README quality, publish readiness, and generating an AI-backed improvement plan via repo-signal. |
| [stack-operations](skills/stack-operations/SKILL.md) | Use when working on mq-agent stack commands — sweep, report, alert, history, cockpit, release-check, release-notes, contract-check, release, loop, brain-gate, truth-export — or the .mq/repo-contract.json stack contract. |
| [visual-analysis](skills/visual-analysis/SKILL.md) | Use when analyzing images, screenshots, or comparing visual assets. Covers object detection, palette extraction, content flags, reverse prompts, UI analysis, and image comparison via mq-image-analyze. |
<!-- END GENERATED SKILLS TABLE -->

## Skill to command mapping

| Skill | Command |
| ----- | ------- |
| repo-audit | `mq-agent audit .` |
| release-readiness | `mq-agent release-check` |
| signal-assessment | `mq-agent signal .` |
| ci-diagnosis | `mq-agent fix-ci` |
| visual-analysis | `mq-image analyze`, `mq-image analyze-ui`, `mq-image compare` |
| mq-mcp-review-orchestration | `mq-agent review file/diff/repo` |
| stack-operations | `mq-agent stack <status\|report\|sweep\|history\|alert\|release-check\|release-notes\|contract-check\|release\|cockpit\|run\|loop\|brain-gate\|truth-export>` |

## Safety modes

All skills respect the safety gate:

| Mode      | Behaviour                          |
|-----------|------------------------------------|
| read-only | Only read tools allowed            |
| suggest   | Plan shown, nothing executed       |
| execute   | Runs after safety check            |
| dangerous | No restrictions                    |

All commands support `--dry-run` and `--json`.
