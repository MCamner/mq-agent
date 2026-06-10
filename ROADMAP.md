# mq-agent Roadmap

v1.4.0 — mq-image-analyze perception tool integration. Done.

## Current status

All planned phases complete through v1.4.0.

| Version | Theme | Status |
| --- | --- | --- |
| v1.4.0 | mq-image-analyze perception tool integration | Done |
| v1.5.0 | End-to-end demo flow | Done |
| v1.6.0 | Stack-wide health | Unscheduled |

## v1.5.0 — End-to-end demo flow

Goal: run the full MQ stack as one verifiable flow, no new features, just integration and documentation.

* [x] `repo-signal readiness` — run signal on one real repo, verify output
* [x] `mq-agent review` — pipe signal result into agent review command
* [x] `mq-mcp contract/release gate` — confirm contract check passes in the flow
* [x] `mqobsidian brain record-review` — write review result as brain note
* [x] `mqlaunch` menu entry — expose the demo flow as a named launch action
* [x] Document the full flow in `docs/DEMO.md` with example output
* [x] Tag v1.5.0 once flow runs clean end-to-end

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full release history.
