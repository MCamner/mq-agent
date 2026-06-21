# Phase 5 — Task-specific context packs

`mq-agent context pack "<task>"` generates a small `context-pack.v1` Markdown
pack for one task, so Codex / Claude Code start from a focused pack instead of
broad READMEs, changelogs, and vault history.

This is the MVP for Phase 5 of the mqobsidian token-reduction roadmap. It builds
directly on Phase 4 (`mq-agent context export`) and Phase 4.5 (CodeGraph source
intelligence).

## What it does

Given a task, the command:

1. **Selects relevant repos** — the `--repo` primary, plus any core MQ repo named
   in the task text, plus `--relevant-repo` extras.
2. **Pulls the mqobsidian context cards** for those repos and points at them
   (`mqobsidian/memory/context-cards/<repo>-card.md`) plus each repo's exported
   `.mq/context/repo-card.md`.
3. **Derives do-not-read guidance** from each card's *Avoid reading unless needed*
   section, so the pack actively steers away from broad first reads.
4. **Adds an optional CodeGraph hint** when the task is source-structure heavy
   (callers / impact / refactor / rename / trace / symbol / fix …). The hint
   names the real index when `.codegraph/` exists in the target repo, and is a
   plain conditional otherwise. Doc-shaped tasks (readme / roadmap / changelog)
   never get a CodeGraph mention.

The output is the existing `context-pack.v1` shape — no new schema.

## Usage

```bash
mq-agent context pack "fix mq-mcp brain writer paths" --repo mq-mcp
mq-agent context pack "update mq-mcp release notes" --repo mq-mcp --codegraph off
mq-agent context pack "trace callers of store_learn_record" \
  --repo mq-mcp --out mq-mcp/.mq/context/task-pack.md
mq-agent context pack "..." --repo mq-mcp --json   # machine-readable selection
```

Flags: `--repo`, `--relevant-repo`, `--relevant-file`, `--note`, `--target`
(`codex|claude|both`), `--vault`, `--repos-root`, `--codegraph` (`auto|on|off`),
`--out`, `--json`.

A worked example pack is in
[`examples/context-packs/fix-mq-mcp-brain-writer-paths.task-pack.md`](../examples/context-packs/fix-mq-mcp-brain-writer-paths.task-pack.md).

## Ownership boundary (how this connects to mqobsidian)

| Concern | Owner |
| --- | --- |
| Durable cards, `context-pack.v1` schema, budgets | **mqobsidian** |
| Task → pack selection, CLI, CodeGraph hinting | **mq-agent** (this) |
| Local source structure (callers/impact) | **CodeGraph** (optional, local) |

mq-agent reads mqobsidian's published cards and renders against mqobsidian's
contract; it does not store durable memory or define the schema. CodeGraph stays
a source-intelligence hint only — never durable memory, never a card. This keeps
Phase 5 consistent with mqobsidian Phase 4.5: the pack does orientation, and
CodeGraph collapses the source-discovery step when a task actually needs it.

## Implementation

* [`mq_agent/tools/context_pack.py`](../mq_agent/tools/context_pack.py) —
  `build_task_pack()` (pure selection + render) and `write_task_pack()`.
* `context pack` command in [`mq_agent/main.py`](../mq_agent/main.py).
* Tests: [`tests/test_context_pack_cmd.py`](../tests/test_context_pack_cmd.py).

The source-heavy heuristic (`task_is_source_heavy`) mirrors
`mqobsidian/scripts/generate-context-pack.py` so both ends agree on when a task
warrants CodeGraph.
