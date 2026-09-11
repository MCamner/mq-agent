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
│ status:       ready                                                          │
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
