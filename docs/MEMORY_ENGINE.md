# Memory Engine — `mq-agent memory`

v1.18.0 makes mqobsidian queryable from mq-agent without requiring an AI call.
The first version is read-only: it scans Markdown notes, builds an in-memory
index, searches locally, summarizes sections, and reports link candidates.

## Commands

```bash
mq-agent memory ingest
mq-agent memory ingest --json

mq-agent memory query "release gate"
mq-agent memory search-vault "release gate" --json

mq-agent memory summarize
mq-agent memory link
```

Use `--vault <path>` to point at a non-default mqobsidian vault. Otherwise the
engine uses `MQ_OBSIDIAN_DIR`, then `~/mqobsidian`.

## Indexed Sections

| Section | Path |
| --- | --- |
| truth | `memory/stack-truth/` |
| reviews | `memory/reviews/` |
| learn | `memory/learn/` |
| releases | `releases/` |
| architecture | `architecture/` |
| decisions | `decisions/` |
| stack-runs | `mq-stack/runs/` |

## Contract

Registered tool names:

```text
memory_ingest
memory_search
memory_summarize
memory_link
```

Safety class: read-only. Link output is advisory; it does not modify notes.
