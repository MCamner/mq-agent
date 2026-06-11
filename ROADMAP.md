# mq-agent Roadmap

v1.13.0 — mqobsidian stack truth export. Done.

## Current status

All planned phases complete through v1.13.0.

| Version | Theme | Status |
| --- | --- | --- |
| v1.8.0 | Stack alert | Done |
| v1.9.0 | Stack report + release gate | Done |
| v1.10.0 | Stack release notes | Done |
| v1.11.0 | Stack contract gate | Done |
| v1.12.0 | CI integration for stack gates | Done |
| v1.13.0 | mqobsidian stack truth export | Done |

## v1.13.0 — mqobsidian stack truth export

Goal: turn stack gate results into durable mqobsidian memory, not transient CI logs.

* [x] `mq-agent stack truth-export` — truth note from contract-check + release-check
* [x] `mq-agent stack export` kept as backwards-compatible alias
* [x] Dated default note path under `~/mqobsidian/memory/stack-truth/`
* [x] `--ci` mode for stack gates; two-job CI workflow (fast PR gate + full stack gate)
* [x] 25 new tests (439 total)
* [x] Tag v1.13.0

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full release history.
