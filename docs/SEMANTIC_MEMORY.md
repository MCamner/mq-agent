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
│ status:       missing-vector-store                                           │
│ vector store: (not set — export OPENAI_VECTOR_STORE_ID)                      │
│ repo-signal:  available                                                      │
│ repo:         /path/to/mq-agent                                              │
╰──────────────────────────────────────────────────────────────────────────────╯

$ mq-agent memory doctor
╭──────────────────────── Memory Doctor ───────────────────────────╮
│ ✗ OPENAI_VECTOR_STORE_ID: (not set)                              │
│   fix: export OPENAI_VECTOR_STORE_ID=vs_...                      │
│ ✓ repo-signal: available                                         │
│ ✓ repo path: /path/to/mq-agent                                   │
╰──────────────────────────────────────────────────────────────────╯

$ mq-agent memory build .
 Would run: repo-signal semantic-upload
Add --no-dry-run to execute, or use memory refresh --approve.

$ OPENAI_VECTOR_STORE_ID=vs_abc mq-agent memory status
╭────────────────────────────── Semantic Memory ───────────────────────────────╮
│ status:       ready                                                          │
│ vector store: vs_abc                                                         │
│ repo-signal:  available                                                      │
│ repo:         /path/to/mq-agent                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
```

---

## Environment

Semantic memory requires a vector store ID:

```bash
export OPENAI_VECTOR_STORE_ID="vs_..."
```

If the variable is not set, `mq-agent memory status` reports the state clearly
and no upload is attempted.

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

### Missing vector store

```text
status: missing-vector-store
```

Fix:

```bash
export OPENAI_VECTOR_STORE_ID="vs_..."
```

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
