# Agent view contract

An **agent view** is a compressed, durable read card that an AI agent (Codex,
Claude Code) reads *first* — before opening a system's full `hot.md`, `index.md`,
or pattern notes. Its only job is to make MQ knowledge **cheaper to consume**:
lower token cost, strict read order. It is a compressed entry surface, not new
primary knowledge.

`mq-agent` owns generation (`mq-agent agent-views rebuild`); `mqobsidian` stores
the result and stays a pure memory layer.

## Location

```text
source:  <vault>/systems/<system>/hot.md
         <vault>/systems/<system>/index.md
         <vault>/memory/learn/repos/<system>.md   (lessons, optional)
output:  <vault>/memory/learn/agent/<system>.md
```

Vault path: `MQ_OBSIDIAN_DIR` env var, else `~/mqobsidian`.

## Hard rules

1. **Pure extraction.** Copy real signals out of the source notes. Never invent
   structure or content that is not in the source.
2. **Never write the source.** `hot.md` / `index.md` are human-curated and are
   never modified — not even to fix cosmetic issues. Only `memory/learn/agent/*.md`
   is written.
3. **Gate on source.** No `hot.md` and no `index.md` → no view. If only one
   exists, build from the one that does.
4. **Idempotent.** Render in memory, compare to the file on disk, write only when
   content differs.
5. **Confined output.** Only write inside `<vault>/memory/learn/agent/`. Any path
   escaping that directory is refused and reported as an error.
6. **Short.** Target ≈120–180 words of body. No raw logs, no long quote blocks,
   no full validation text. When over budget, shed lowest-value content first
   (lessons, then the priorities tail) — never the source.

## Card structure

```md
---
type: agent-view
system: <system>
generated: <YYYY-MM-DD>
generator: mq-agent agent-views rebuild
sources: [systems/<system>/hot.md, systems/<system>/index.md, ...]
---

# <system> — agent view

## Current state
One compact paragraph (hot mission/status first, index state as fallback).

## Active priorities
- up to 4 items (index priorities, else hot immediate next actions)

## Current blockers
- hot blockers + index risks, or "none"

## Relevant lessons
- up to 3 short lesson references (from memory/learn/repos/<system>.md; omitted if absent)

## Read next
- [[systems/<system>/hot]]
- [[systems/<system>/index]]
```

## Report shape

`rebuild_agent_views()` returns:

```json
{
  "vault": "…",
  "output_dir": "…",
  "dry_run": false,
  "repos_checked": 5,
  "views_written": ["…"],
  "views_updated": ["…"],
  "views_unchanged": ["…"],
  "views_skipped_no_source": ["…"],
  "errors": []
}
```

## Phasing

- **A (done):** manual, testable `agent-views rebuild` with this contract.
- **B (done):** run once for real → `mq-agent` is the canonical owner; the
  vault-local prototype generator is retired.
- **C (done):** trigger rebuild where source changes, and guard against drift.
  - Stack-wide opt-in flag — `mq-agent stack truth-export --rebuild-views` —
    never default.
  - Surgical single-system trigger — `mq-agent agent-views rebuild --system
    <system>` — wired as the last step of the `mq-hot-refresh` /
    `mq-index-refresh` flows in mqobsidian, so a view is refreshed exactly where
    its `hot.md` / `index.md` source was just rewritten.
  - Drift guard — `mq-agent agent-views check [--system <system>]` — rebuilds in
    dry-run, writes nothing, and exits non-zero if any view is stale vs its
    source (CI-friendly). This is the precondition for ever defaulting the
    rebuild on: drift is now detectable, not silent.
  - **Deliberately not built:** a background watcher / daemon. The trigger is
    explicit (skill flows + the drift check), keeping the system deterministic
    and idempotent with no long-running process to own.
