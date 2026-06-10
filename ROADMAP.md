# mq-agent Roadmap

v1.7.0 — Repo health history. Done.

## Current status

All planned phases complete through v1.7.0.

| Version | Theme | Status |
| --- | --- | --- |
| v1.5.0 | End-to-end demo flow | Done |
| v1.6.0 | Stack-wide health | Done |
| v1.7.0 | Repo health history | Done |

## v1.7.0 — Repo health history

Goal: persist every `stack sweep` result and expose trend + diff commands.

* [x] `stack sweep` appends to `~/.mq-agent/sweep-history.jsonl`
* [x] `mq-agent stack history` — tabular trend view
* [x] `mq-agent stack history --diff` — delta between last two sweeps
* [x] `mq-agent stack history --json` / `--limit N`
* [x] `docs/STACK_HISTORY.md` — reference with JSONL schema and jq examples
* [x] Tag v1.7.0

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full release history.
