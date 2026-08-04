# Canonical Semantic Memory Plan

## Goal

Give mq-agent a canonical semantic memory it owns in tracked code, and settle
whether the `macos-scripts-knowledge` store holds anything that would be lost
if it were retired.

This is step (b) of a four-step plan to move `ask` and `chat` off macos-scripts.
Routing is deliberately untouched until the memory question is closed.

## Owner repo

mq-agent

## Secondary repos

- macos-scripts — owns `ask`/`fix`/`chat`/`hal-terminal-guide` today. Not changed here.
- mq-mcp — owns `GLOBAL_VECTOR_STORE_POLICY.md`. Not changed here.
- mqobsidian — received the six rescued guides (2026-08-03). Not changed here.

## Architecture boundary

- mq-agent declares which store is canonical; it does not decide what any other
  repo's CLI points at.
- The store ID is an addressable name and belongs in tracked code. The API key
  is the secret and stays in `.env`.
- No upload, deletion, or store mutation happens in this scope.

## Non-goals

- Moving `ask` or `chat` (step c).
- Retiring `fix` (step d).
- Deleting the `macos-scripts-knowledge` store.

## What changed

`mq_agent/memory/semantic.py` declares `CANONICAL_VECTOR_STORE_ID`
(`vs_69ffa9a4ef5c81919d7d237c3ecdc260`, "semantic repository memory") and adds
`resolve_vector_store_id() -> (id, source)`. An explicit
`OPENAI_VECTOR_STORE_ID` still wins; otherwise the canonical store applies.

`status` and `doctor` report which store answered and where the ID came from,
so the fallback is never silent. The `missing-vector-store` state is gone —
mq-agent is never without a memory.

### Why this was needed

The canonical ID existed only in gitignored `.env` files:

| Location | Value |
|---|---|
| `~/mq-agent/.env` | canonical (gitignored) |
| `~/macos-scripts/.env` | canonical (gitignored) |
| `~/.env` | does not exist |
| `~/.zshrc` | not set |

`mq-mcp/.env` is described as "the primary" in `GLOBAL_ARCHITECTURE_NOTES.md`
but does not exist on this machine — documentation drift worth correcting in
mq-mcp separately.

So the identity of mq-agent's memory depended on an untracked file in the very
repo whose scripts are due to be retired. Meanwhile all four macos-scripts
consumers hardcode `vs_69f93de1…` as their fallback, which is a *different*
store — the one that resolves whenever those `.env` files are absent.

## Store inventory (read-only, 2026-08-04)

| Store | ID | Files | Bytes | Last active |
|---|---|---|---|---|
| semantic repository memory | `vs_69ffa9a4…` | 211 | 3.4 MB | 2026-07-16 |
| macos-scripts-knowledge | `vs_69f93de1…` | 101 | 2.2 MB | 2026-06-18 |

Filename overlap between the two is zero, but that is a naming artifact, not
evidence of unique content: canonical uses the policy's flattened
`{repo}__{path}.ext` convention, the other uses bare names.

Content classification of all 101 files:

| Class | Count | Disposition |
|---|---|---|
| Has a source path in git history | 89 | Regenerable |
| Repo sources the name heuristic missed (`workflow-*`, `tools-scripts-README`) | 3 | Regenerable |
| `mac-terminal-guide.md` | 1 | Generated view of tracked HTML — see below |
| `upload-manifest.md` | 1 | The store's own bookkeeping |
| `ask.sh.md` | 1 | Rendering of `tools/scripts/ask.sh` |
| Swedish command guides | 6 | **Not in any repo** — rescued 2026-08-03 |

`upload-manifest.md` (dated 2026-06-18) is the store's own provenance record.
It lists `Source: /Users/mansys/macos-scripts` and maps every uploaded filename
back to a repo path, which independently confirms the classification above.

### mac-terminal-guide.md

62184 bytes, the largest file, and the only entry whose source was not obvious.
`docs/mac-terminal-guide.html` is tracked but yields just 98 bytes of static
text — the content lives in a `const COMMANDS` array of 297 commands inside a
275 KB script block.

OpenAI blocks downloading files with `purpose: assistants`, so the file could
not be fetched. Its content was read instead through `file_search` with
`include: ["file_search_call.results"]`, which returns raw chunk text. Eight
distinct strings sampled from those chunks — including
`Prevent the Mac from sleeping during a troubleshooting session` and
`Säkerhet & Kryptering` — all appear verbatim in the tracked HTML. The size
matches a rendering that uses the English description fields (55289 bytes of
field text plus markdown headings and fences).

It is a generated view of tracked data. Nothing unique.

### Conclusion

The `macos-scripts-knowledge` store contains nothing that is not either in git
or already preserved in mqobsidian. There is no content left to migrate, so
step (c) is unblocked on the memory question.

## Precondition before that store can be retired

`macos-scripts/tools/scripts/hal-terminal-guide.sh` reads
`MQ_TERMINAL_GUIDE_VECTOR_STORE_ID` and falls back to `vs_69f93de1…` with no
`.env` sourcing and no canonical fallback — it uses that store
unconditionally. `ask.sh`, `fix.sh`, and `chat.sh` name the same store as their
last-resort fallback.

Retiring the store before those four are repointed would break the terminal
guide silently.

## Verification

```text
$ HOME=<empty> OPENAI_VECTOR_STORE_ID unset  mq-agent memory status .
status:       ready
vector store: vs_69ffa9a4ef5c81919d7d237c3ecdc260 (canonical)
```

1053 tests pass; ruff and markdownlint clean. Both halves of the new contract
were checked against planted defects: breaking the canonical fallback and
ignoring the env override each turn six tests red.
