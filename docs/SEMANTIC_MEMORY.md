# Semantic repository memory

mq-agent v0.5.0 adds semantic repository memory.

The goal is to let mq-agent use persistent repo knowledge when auditing,
checking releases and planning improvements.

```text
repo files
  ↓
repo-signal semantic memory
  ↓
mq-agent memory status / build / refresh
  ↓
audit / release-check / score with repo context
```

---

## Commands

```bash
mq-agent memory status          # configured / reachable / freshness / generation counts
mq-agent memory doctor          # diagnose environment with actionable fixes
mq-agent memory build .         # dry-run semantic upload (safe default)
mq-agent memory refresh . --approve  # first generation / no competing retrieval state
mq-agent memory refresh . --approve --cleanup-stale  # explicit latest-only replacement
mq-agent memory status --json   # machine-readable output
mq-agent memory doctor --json   # machine-readable diagnostics
```

### Example output

```text
$ mq-agent memory status
╭────────────────────────────── Semantic Memory ───────────────────────────────╮
│ status:       degraded                                                       │
│ configured:   true                                                           │
│ reachable:    unknown                                                        │
│ freshness:    unknown                                                        │
│ vector store: vs_69ffa9a4ef5c81919d7d237c3ecdc260 (canonical)                │
│ active gens:  unknown                                                        │
│ outside auth: unknown                                                        │
│ latest upload: unknown                                                       │
│ repo-signal:  available                                                      │
│ repo:         /path/to/mq-agent                                              │
╰──────────────────────────────────────────────────────────────────────────────╯

$ mq-agent memory doctor
╭──────────────────────────── Memory Doctor ───────────────────────────────────╮
│ ✓ vector store: vs_69ffa9a4ef5c81919d7d237c3ecdc260 (canonical)              │
│ ✓ repo-signal: available                                                     │
│ ✓ repo path: /path/to/mq-agent                                               │
╰──────────────────────────────────────────────────────────────────────────────╯

$ mq-agent memory build .
 Would run: repo-signal semantic-upload
Add --no-dry-run to execute, or use memory refresh --approve.

$ OPENAI_VECTOR_STORE_ID=vs_abc mq-agent memory status
╭────────────────────────────── Semantic Memory ───────────────────────────────╮
│ status:       degraded                                                       │
│ configured:   true                                                           │
│ reachable:    unknown                                                        │
│ freshness:    unknown                                                        │
│ vector store: vs_abc (OPENAI_VECTOR_STORE_ID)                                │
│ repo-signal:  available                                                      │
│ repo:         /path/to/mq-agent                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
```

---

## Which store answers

mq-agent owns a canonical store and always has a memory. The id is declared in
`mq_agent/memory/semantic.py`, not recovered from the machine:

| Source | When it applies | Reported as |
| --- | --- | --- |
| `OPENAI_VECTOR_STORE_ID` | set to a non-empty value | `OPENAI_VECTOR_STORE_ID` |
| canonical | unset, empty, or whitespace-only | `canonical` |

```bash
# point a command at a different store, for one run
OPENAI_VECTOR_STORE_ID="vs_..." mq-agent memory status
```

`status`, `doctor` and both `--json` outputs always name which of the two
applied, so a fallback is never silent.

Resolution reads the process environment and nothing else. There is no `.env`
discovery and no shell-out, so the store cannot change with the directory a
command happens to run in. A store id is an addressable name, not a credential;
the API key stays out of the repository.

The canonical id is `vs_69ffa9a4ef5c81919d7d237c3ecdc260`.

---

## Safety model

mq-agent never uploads memory silently.

| Command                      | Behavior              |
|------------------------------|-----------------------|
| `memory status`              | read-only             |
| `memory build .`             | dry-run by default    |
| `memory build . --no-dry-run`| routes through latest-only refresh safety |
| `memory refresh . --approve` | uploads only when no competing retrieval generation exists |
| `memory refresh . --approve --cleanup-stale` | uploads, verifies, then detaches stale retrieval generations |

---

## Recommended flow

```bash
# 1. Check what's available
mq-agent memory status

# 2. Preview what would be uploaded
mq-agent memory build .

# 3. Upload when ready. Existing/stale generations need explicit replacement.
mq-agent memory refresh . --approve --cleanup-stale
```

---

## Failure states

### Missing repo-signal

```text
status: degraded
repo-signal: not found
```

Fix:

```bash
uv pip install repo-signal
```

---

## Design principle

Semantic memory should make mq-agent more context-aware without making it
less predictable. No memory action happens invisibly.

## Freshness contract

`memory status` no longer uses `ready` as a synonym for "configured".

- `configured`: an authoritative vector-store id is resolved.
- `reachable`: OpenAI metadata could be read with the process credential.
- `freshness`: `fresh`, `stale`, or `unknown`.
- `ready`: only when the store is reachable, exactly one authoritative
  generation exists, no non-authoritative retrieval generation is present,
  the stored `source_revision` equals the repo HEAD, and repo-signal is
  available.

Historical generations without `source_revision` are `unknown`, never
silently fresh. Multiple completed generations are `stale`.

## Latest-only replacement

A refresh that would append beside an existing retrieval generation is refused
before upload unless `--cleanup-stale` is present. With that explicit flag,
mq-agent uploads first, verifies the new completed generation, writes
`source_revision` metadata, and only then detaches stale vector-store
attachments. Because OpenAI list/delete visibility can converge shortly after a
successful detach, refresh verifies the postcondition with a bounded retry
window before reporting failure. Underlying OpenAI Storage file objects are
retained.

Retired stores are eligible only for identity-scoped symbol-memory cleanup:

- macos-scripts: `vs_69f93de12f508191bd6a36ea3b825beb`, after its
  tracked resolver regression test proved consumers migrated to canonical.
- mq-mcp: `vs_6a0513bc1adc8191bc18affe4383d83f`, after mq-mcp
  PR #88 migrated `ask` to canonical memory.

Cleanup never treats those store IDs as authority to remove unrelated files.
Only files matching the target repo + symbol-memory identity are detached.
