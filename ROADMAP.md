# mq-agent Roadmap

v1.15.0 — brain-integrated stack workflow. Released.
Next: v1.16.0 — Runtime consolidation.

## Current status

All phases complete through v1.15.0.

| Version | Theme | Status |
| --- | --- | --- |
| v1.8.0 | Stack alert | Done |
| v1.9.0 | Stack report + release gate | Done |
| v1.10.0 | Stack release notes | Done |
| v1.11.0 | Stack contract gate | Done |
| v1.12.0 | CI integration for stack gates | Done |
| v1.13.0 | mqobsidian stack truth export | Done |
| v1.14.0 | Stack release orchestration | Done |
| v1.15.0 | Brain-integrated stack workflow | Done |
| v1.16.0 | Runtime consolidation | Planned |
| v1.17.0 | Ollama runtime | Planned |
| v1.18.0 | Memory engine | Planned |
| v1.19.0 | Operator dashboard | Planned |
| v1.20.0 | Autonomous stack | Planned |

## v1.16.0 — Runtime consolidation

Goal: keep mq-agent focused as the orchestrator while reducing parallel paths.

The rule remains:

```text
mqlaunch → starts
mq-agent → orchestrates
mq-mcp → runs
repo-signal → measures
mqobsidian → remembers
ollama → reasons
mq-hal → presents
```

* [ ] Consolidate overlapping entrypoints where `signal`, `review`, `learn`,
  and `truth-export` duplicate the same operator flow.
* [ ] Define one canonical orchestration pipeline:
  inspect → review → extract → learn → truth-export → release.
* [x] Add `mq-agent stack run` as the first stack runtime surface with
  `--dry-run`, `--json`, `--brain`, `--ci`, and `--approve`; expose it from
  the canonical root surface as `mq-agent run --stack`.
* [x] Add `docs/MQ_CONTROL_PLANE.md` — one system map for signal, review,
  learn, memory and release.

## Planned after v1.16.0

* [ ] v1.17.0 — Ollama runtime: first-class `mq-agent models` commands.
* [ ] v1.18.0 — Memory engine: ingest, search, summarize, and link memory.
* [ ] v1.19.0 — Operator dashboard: TUI for stack health, release, brain,
  Ollama, repos, and contracts.
* [ ] v1.20.0 — Autonomous stack: tighter contracts and controlled stack loops.

## v1.15.0 — Brain-integrated stack workflow

Goal: make mq-agent the stable conductor of the full loop —
repo status → review → learn extract → brain write → stack truth export
→ next action. mq-agent orchestrates; mq-mcp thinks/runs, repo-signal
measures, mqobsidian remembers, mqlaunch launches.

* [x] `mq-agent stack cockpit` — one table for the whole stack:
  repo, status, branch, dirty, version, contract, release gate,
  brain export freshness, next action. Later the input to mq-hal.
* [x] Consistent flag behaviour across write-capable commands:
  `--dry-run` never writes, `--json` machine-readable, `--brain`
  never writes without an explicit command, `--approve` required
  for write flows.
* [x] Standard mqobsidian export structure: `memory/stack-truth/`,
  `memory/reviews/`, `memory/learn/`, `mq-stack/runs/`, `mq-stack/roadmaps/`
  — `mq-agent brain structure` (check / `--init --approve`)
* [x] Brain release gate: `mq-agent stack brain-gate` — `contract-check` +
  `release-check` + truth-export dry-run + vault structure + the
  review→brain write path, all green before release
* [x] Docs sync: README, docs/ROADMAP, MQ_ECOSYSTEM, CHANGELOG, repo-contract
* [x] Tag v1.15.0

## v1.14.0 — Stack release orchestration

Goal: close the loop. The stack suite observes (`status`, `report`, `sweep`,
`history`), gates (`alert`, `release-check`, `contract-check`), remembers
(`truth-export`), and drafts (`release-notes`) — but the release itself is
still manual, per repo, across 7 repos. `stack release` makes the pipeline act.

* [x] `mq-agent stack release --repo <name>` — orchestrated single-repo release:
  release-check as pre-gate, version bump, changelog update from the
  release-notes draft, tag, push
* [x] Dry-run by default (same pattern as `sweep`); `--execute` to apply
* [x] `--json` — machine-readable output for CI
* [x] Automatic `truth-export` after a successful release, so the release
  lands in mqobsidian memory
* [x] Abort cleanly on any failed step — no half-released repos
* [x] `docs/STACK_RELEASE.md` — reference doc
* [x] Tests for gate refusal, dry-run plan, step failure rollback (27 tests)
* [x] Tag v1.14.0

## v1.13.0 — mqobsidian stack truth export

Goal: turn stack gate results into durable mqobsidian memory, not transient CI logs.

* [x] `mq-agent stack truth-export` — truth note from contract-check + release-check
* [x] `mq-agent stack export` kept as backwards-compatible alias
* [x] Dated default note path under `~/mqobsidian/memory/stack-truth/`
* [x] `--ci` mode for stack gates; two-job CI workflow (fast PR gate + full stack gate)
* [x] 25 new tests (439 total)
* [x] Tag v1.13.0

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full release history.
