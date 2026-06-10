# mq-agent Roadmap

v1.8.0 — Stack alert. Done.

## Current status

All planned phases complete through v1.8.0.

| Version | Theme | Status |
| --- | --- | --- |
| v1.6.0 | Stack-wide health | Done |
| v1.7.0 | Repo health history | Done |
| v1.8.0 | Stack alert | Done |

## v1.8.0 — Stack alert

Goal: threshold-based alerting when repos regress between sweeps.

* [x] `mq-agent stack alert` — exits 1 on drop ≥ threshold or below min-score
* [x] `mq-agent stack sweep --alert` — inline alert at end of sweep
* [x] `--threshold N` / `--min-score N` — configurable
* [x] `--json` — machine-readable, CI-friendly
* [x] `docs/STACK_ALERT.md` — reference with CI integration
* [x] Tag v1.8.0

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full release history.
