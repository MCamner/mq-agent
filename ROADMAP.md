# mq-agent Roadmap

v1.6.0 — Stack-wide health sweep. Done.

## Current status

All planned phases complete through v1.6.0.

| Version | Theme | Status |
| --- | --- | --- |
| v1.4.0 | mq-image-analyze perception tool integration | Done |
| v1.5.0 | End-to-end demo flow | Done |
| v1.6.0 | Stack-wide health | Done |

## v1.6.0 — Stack-wide health

Goal: run repo-signal over every core MQ repo in one sweep, write brain notes per
repo and an optional consolidated health ADR.

* [x] `mq-agent stack sweep` — loop repo-signal over all mq-stack repos
* [x] `mq-agent stack sweep --brain` — brain note per repo
* [x] `mq-agent stack sweep --decide` — consolidated ADR snapshot
* [x] mqlaunch agent menu item 18 — Stack health sweep
* [x] `docs/STACK_HEALTH.md` — reference doc with example output
* [x] Tag v1.6.0

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full release history.
