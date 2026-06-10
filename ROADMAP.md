# mq-agent Roadmap

v1.12.0 — CI integration for stack gates. Done.

## Current status

All planned phases complete through v1.12.0.

| Version | Theme | Status |
| --- | --- | --- |
| v1.6.0 | Stack-wide health | Done |
| v1.7.0 | Repo health history | Done |
| v1.8.0 | Stack alert | Done |
| v1.9.0 | Stack report + release gate | Done |
| v1.10.0 | Stack release notes | Done |
| v1.11.0 | Stack contract gate | Done |
| v1.12.0 | CI integration for stack gates | Done |

## v1.12.0 — CI integration for stack gates

Goal: run the stack contract gate and release gate automatically in GitHub Actions.

* [x] `.github/workflows/mq-stack-gate.yml` — gates on PRs and pushes to main
* [x] `mq-agent stack contract-check --ci` — missing sibling repos SKIPPED instead of BLOCKED
* [x] `mq-agent stack release-check --ci` — missing sibling repos do not block
* [x] CI checkout detected via workspace directory name and validated fully
* [x] 21 new tests (429 total)
* [x] Tag v1.12.0

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full release history.
