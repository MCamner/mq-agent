<!--
mq-template-lineage: superset-v1
Generated from mqobsidian agent-entrypoint templates for mq-agent.
Do not hand-edit this file directly; edit the mqobsidian templates and regenerate.

Ownership model:
- mqobsidian owns the contract, templates, schemas, and generators.
- this repo owns this committed agent surface once published.

Paths use the portable $MQ_OBSIDIAN_DIR placeholder; resolve it to your local
mqobsidian checkout. Regenerate with:
  MQ_OBSIDIAN_DIR=<path-to-mqobsidian> \
    python3 "$MQ_OBSIDIAN_DIR"/scripts/generate-agents-md.py --repo mq-agent --out AGENTS.md
-->

# AGENTS.md

This repo is part of the MQ stack.

These instructions add MQ memory read-order rules. They do not replace
repo-specific build, test, safety, or release instructions.

## mqobsidian Location

Default local vault path: `$MQ_OBSIDIAN_DIR`. If `MQ_OBSIDIAN_DIR` is set,
prefer that value.

## Read First

For work related to `mq-agent`:

1. Read `.mq/context/task-pack.md` if it exists and matches the task.
2. Read `.mq/context/repo-card.md` if it exists.
3. Read `.mq/context/integration-map.md` if it exists.
4. Read `$MQ_OBSIDIAN_DIR/memory/learn/agent/mq-agent.md` if it exists.
5. Read `$MQ_OBSIDIAN_DIR/systems/mq-agent/hot.md` if it exists.
6. Read `$MQ_OBSIDIAN_DIR/systems/mq-agent/index.md` if it exists.
7. Read `$MQ_OBSIDIAN_DIR/memory/learn/repos/mq-agent.md` if it exists.
8. Read individual pattern notes only if the compressed notes are insufficient.

Stop reading as soon as the task is grounded.

## Low-Token Rules

- Prefer task packs and agent views over full notes.
- Prefer hot/index over pattern notes.
- Do not scan the whole vault by default.
- Do not open multiple pattern notes unless clearly needed.
- Summarize instead of replaying long note bodies.

## Rules

- Do not duplicate logic owned by another MQ repo.
- Prefer JSON contracts over free-text coupling.
- Keep repo boundaries explicit.
- Use `mqobsidian` only as durable memory, not runtime truth.
- Verify current code behavior, tests, contracts, and CLI behavior in this repo.

## Durable Memory

MQ-stack memory lives in `mqobsidian`. Use generated context packs before
reading large docs.

`mqobsidian` is durable memory, not live runtime truth. If the task depends on
current code behavior, tests, contracts, CLI behavior, or runtime state, verify
in this repo before making claims.

## Source Intelligence

If `.codegraph/` exists, use CodeGraph MCP before broad scans:
`codegraph_context` first; use trace/explore/impact as the task requires.
Treat returned source as read; use targeted reads only for missing, stale, or
unsupported detail. Use `mqobsidian` for durable memory and repo boundaries.

## Writing Rules

When creating notes, summaries, or exports:

- separate facts, interpretation, and recommendation
- keep outputs compact
- preserve timestamps and provenance when relevant
- prefer links over duplicated prose
- avoid raw dumps

Do not store or copy secrets, tokens, internal hostnames, raw enterprise logs,
or machine-specific private paths.

## MQ Skills

Repo-local skills live under `.agents/skills/` (Codex) and `.claude/skills/`
(Claude Code). Route by each skill's frontmatter `description`. A few are
near-universal across MQ repos:

- `mq-writing-plans` — before multi-step or cross-repo changes.
- `mq-worktree-safe` — before risky branch/worktree flows.
- `mq-secrets-public-safe` — before publishing, commit, or PR.

Use any other installed skill when its description matches the task.

## Fallback Rule

If `mqobsidian` is missing, stale, or too weak for the task, say so and verify
in the repo. Do not invent continuity.

---

## AGENTS.md — Governor (mansys/mcamner)

<!-- Läggs i repo-roten eller ~/.codex/AGENTS.md. Codex läser den per session, som CLAUDE.md. -->

## Kommunikation

- Svara på svenska om inget annat sägs. Kort och direkt. Ingen hype, inga superlativ.
- Ärlig bedömning före artighet. Säg "det här är en dålig idé" när det är det, med skäl.
- Osäkerhet: säg "kan inte bekräfta" istället för att gissa. Hitta aldrig på källor, siffror eller API:er.

## Kod

- Kirurgiska ändringar. Rör inte kod utanför uppgiften. Ingen "passade på att refaktorera".
- Inga onödiga abstraktioner. Enklaste lösning som håller.
- Redovisa antaganden explicit innan implementation. Definiera verifierbart framgångskriterium.
- Verifiera innan du deklarerar klart: kör testet, läs outputen, visa beviset.
- TDD vid features och bugfixar där det är rimligt: test först.
- Läs faktiska filer i repot istället för att gissa struktur.

## Arbetssätt

- Kör vidare på självklara nästa steg utan att fråga. Fråga endast vid destruktiva operationer (delete, force-push, prod).
- Vid felsökning: reproducera → isolera → diagnostisera → fixa. Inte "prova det här och se".
- En fråga i taget om förtydligande behövs, och bara om svaret inte redan finns i kontexten.

## Miljö

- macOS: MQ-stacken. mq-mcp är MCP-servern (hal_repo_report, read_repo_file, run_mqlaunch_doctor, record_learning). Bridget är agenten (bridge.py, bridget_context.py). Repon: mq-mcp, mq-agent, mq-hal, macos-scripts, mqobsidian.
- Windows (Region Stockholm): PowerShell-svit med mongo-prefix (mongostart, mongoApps, mongoSys, mongoKommand, loggMongo). GPO-begränsad miljö — räkna med workarounds.
- Fedora-testmaskin (Dell Latitude 5290): Fish/bash.
- IT-domän: IGEL OS 12, UMS, Citrix CVAD, Intune/Entra ID. Svensk offentlig sektor/vård — säkerhet och spårbarhet väger tungt.

## Konventioner

- Namnprefix: mq- (macOS), mongo- (Windows).
- Estetik: JetBrains Mono, amber/dark terminal, HAL 9000/Amiga-tema.
- Dokumentation ofta bilingualt SV/EN.
