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
mq-agent memory status          # check vector store and repo-signal availability
mq-agent memory doctor          # diagnose environment with actionable fixes
mq-agent memory build .         # dry-run semantic upload (safe default)
mq-agent memory refresh . --approve  # upload semantic memory (requires approval)
mq-agent memory status --json   # machine-readable output
mq-agent memory doctor --json   # machine-readable diagnostics
```

### Example output

```text
$ mq-agent memory status
╭────────────────────────────── Semantic Memory ───────────────────────────────╮
│ status:       ready                                                          │
│ vector store: vs_69ffa9a4ef5c81919d7d237c3ecdc260 (canonical)                │
│ repo-signal:  available                                                      │
│ repo:         /path/to/mq-agent                                              │
╰──────────────────────────────────────────────────────────────────────────────╯

$ mq-agent memory doctor
╭─────────────────────────────── Memory Doctor ────────────────────────────────╮
│ ✓ vector store: vs_69ffa9a4ef5c81919d7d237c3ecdc260 (semantic repository     │
│ memory, canonical default)                                                   │
│ ✓ repo-signal: available                                                     │
│ ✓ repo path: /path/to/mq-agent                                               │
╰──────────────────────────────────────────────────────────────────────────────╯

$ mq-agent memory build .
 Would run: repo-signal semantic-upload
Add --no-dry-run to execute, or use memory refresh --approve.

$ OPENAI_VECTOR_STORE_ID=vs_abc mq-agent memory status
╭────────────────────────────── Semantic Memory ───────────────────────────────╮
│ status:       ready                                                          │
│ vector store: vs_abc (OPENAI_VECTOR_STORE_ID)                                │
│ repo-signal:  available                                                      │
│ repo:         /path/to/mq-agent                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
```

---

## The canonical store

mq-agent owns the canonical semantic memory:

| | |
|---|---|
| name | `semantic repository memory` |
| id | `vs_69ffa9a4ef5c81919d7d237c3ecdc260` |
| declared in | `mq_agent/memory/semantic.py` |
| policy | `mq-mcp/docs/global/GLOBAL_VECTOR_STORE_POLICY.md` |

The ID lives in tracked code on purpose. It used to exist only in gitignored
`.env` files, which meant a machine without that file had either no memory at
all or whatever store an ambient variable happened to name. A vector-store ID
is an addressable name, not a secret; the API key is the secret, and that stays
in `.env`.

`status` and `doctor` always report which store answered and where the ID came
from — `(canonical)` or `(OPENAI_VECTOR_STORE_ID)` — so a fallback is never
silent.

---

## Environment

Semantic memory needs no configuration. Set the variable only to point a repo
at a store other than the canonical one:

```bash
export OPENAI_VECTOR_STORE_ID="vs_..."
```

An explicit value always wins. There is no longer a `missing-vector-store`
state, because mq-agent is never without a memory.

---

## Safety model

mq-agent never uploads memory silently.

| Command                      | Behavior              |
|------------------------------|-----------------------|
| `memory status`              | read-only             |
| `memory build .`             | dry-run by default    |
| `memory build . --no-dry-run`| uploads after prompt  |
| `memory refresh . --approve` | uploads (gate open)   |

---

## Recommended flow

```bash
# 1. Check what's available
mq-agent memory status

# 2. Preview what would be uploaded
mq-agent memory build .

# 3. Upload when ready
mq-agent memory refresh . --approve
```

---

## Failure states

Only one remains. The store can no longer be missing — see
[The canonical store](#the-canonical-store).

### Missing repo-signal

```text
status: missing-repo-signal
```

Fix:

```bash
uv pip install repo-signal
```

---

## Design principle

Semantic memory should make mq-agent more context-aware without making it
less predictable. No memory action happens invisibly.
