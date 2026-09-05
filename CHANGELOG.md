# Changelog

All notable changes to mq-agent are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

## [v1.27.0] — 2026-09-05

* ebe80c9 chore(release): prepare v1.27.0 and renumber the roadmap (#259)
* c0bfd3c feat(routing): open the evidence-integrity era (#258)
* 2269309 docs(roadmap): record the execution evidence integrity work (#257)
* 6d9dd36 fix(evidence): a runtime that cannot be identified writes no production evidence (#256)
* bc74d17 fix(cli): a run that never started is not a failed execution (#255)
* fc8f821 feat(routing): a model that ran out of time was not unavailable (#254)
* 8a43900 fix(routing): give the local route a budget its slow draws can finish inside (#253)
* afb7af5 docs(roadmap): record operational verification of the verifier excerpt fix (#252)
* 9567066 docs(roadmap): record verifier excerpt integrity fix (#250) (#251)
* 92688b1 fix: separate verifier excerpts from execution completeness (#250)
* c7c95e7 feat(routing): open the collection-integrity era (#249)
* 1dcb973 fix: enforce declared collection integrity (#248)
* 7f34a4b fix: back two claims the code did not actually make (#246)
* 522687a feat(routing): open the era in which a review reads what it declared (#245)
* a232fbb fix(docs): tell the audit what it is auditing (#244)
* 3be9b0d feat(routing): open the era in which a review cannot be handed a secret (#243)
* 49e6c67 fix(tools): stop offering secret files to a reader (#241)
* dae09cf feat(routing): open the era in which a docs-review reads what it planned to (#239)
* 6c67086 feat(executor): make a plan dependency something the runtime can execute (#238)
* aa0c09f feat(planner): tell the planner what the tools actually take (#236)
* c4d2f67 feat(routing): record the plan-validation era at its real merge point (#234)
* 0a1721b fix(executor): reject a call the tool cannot accept, before making it (#233)
* 28f12e4 feat(routing): report how two routes differ, at two levels and without a verdict (#231)
* 16b1997 feat(routing): make the quality population expressible without touching readiness (#230)
* 7fe49bf feat(routing): give a routed decision only what it can finish reading (#227)
* d34e1dd fix(routing): give the model the material the verifier checks against (#226)
* 25490f6 chore(contracts): sync the vendored route outcome to canonical (#225)
* 8a55d4d fix(routing): pin the task class in the grammar instead of asking for it (#224)
* 1e89ca6 feat(routing): add a second applied route that runs no model (ADR-010 D8) (#223)
* a55c7f3 chore(contracts): sync the vendored route outcome to canonical (ADR-010 D8) (#222)
* 6e9daf2 fix(routing): bound evidence by what verifies, not by how much the model writes (#221)
* 52d7b5f feat(routing): apply a route for real, and move readiness to the routing layer (#220)
* 97afe21 feat(contracts): vendor D6/D7 and stop the swarm claiming a route (#219)
* 741615f chore(contracts): vendor the routing contract's execution correlation (#218)
* f909c4a feat(contracts): vendor canonical contracts and gate them against mqobsidian (#216) (#217)
* 8b2b4a3 feat(telemetry): record the model an execution actually used (#213) (#215)
* bb9a8be feat: mq.execution-outcome.v1 — contract, one truthful emit point, and separate reporting (#206)
* c1b0b4a fix(context): state CodeGraph intentions, never tool names (#212)
* c6b8035 feat(context): read the selection vocabulary from mqobsidian (#211)
* 18888da feat: record how much evidence was grounded, not just pass/fail (#210)
* 7445075 feat: emit feedback-signal.v1 pack-usage records (#209)
* 4b281ef fix: emit plain-text source headers, not HTML comments (#208)
* b3870ff feat: build local notebook packs from mqobsidian's profile (#207)
* d16a5c4 fix: resolve repo-signal from uv tool runtime
* 589b629 docs: sync roadmaps after v1.26.0 and open v1.27.0 (#204)

Theme: execution instrumentation and evidence integrity. Every significant run
now leaves one outcome record, and the work that followed made those records —
and the routing evidence beside them — say only what the runtime can actually
prove.

* c0bfd3c feat(routing): open the evidence-integrity era (#258)
* 2269309 docs(roadmap): record the execution evidence integrity work (#257)
* 6d9dd36 fix(evidence): a runtime that cannot be identified writes no production evidence (#256)
* bc74d17 fix(cli): a run that never started is not a failed execution (#255)
* fc8f821 feat(routing): a model that ran out of time was not unavailable (#254)
* 8a43900 fix(routing): give the local route a budget its slow draws can finish inside (#253)
* afb7af5 docs(roadmap): record operational verification of the verifier excerpt fix (#252)
* 9567066 docs(roadmap): record verifier excerpt integrity fix (#250) (#251)
* 92688b1 fix: separate verifier excerpts from execution completeness (#250)
* c7c95e7 feat(routing): open the collection-integrity era (#249)
* 1dcb973 fix: enforce declared collection integrity (#248)
* 7f34a4b fix: back two claims the code did not actually make (#246)
* 522687a feat(routing): open the era in which a review reads what it declared (#245)
* a232fbb fix(docs): tell the audit what it is auditing (#244)
* 3be9b0d feat(routing): open the era in which a review cannot be handed a secret (#243)
* 49e6c67 fix(tools): stop offering secret files to a reader (#241)
* dae09cf feat(routing): open the era in which a docs-review reads what it planned to (#239)
* 6c67086 feat(executor): make a plan dependency something the runtime can execute (#238)
* aa0c09f feat(planner): tell the planner what the tools actually take (#236)
* c4d2f67 feat(routing): record the plan-validation era at its real merge point (#234)
* 0a1721b fix(executor): reject a call the tool cannot accept, before making it (#233)
* 28f12e4 feat(routing): report how two routes differ, at two levels and without a verdict (#231)
* 16b1997 feat(routing): make the quality population expressible without touching readiness (#230)
* 7fe49bf feat(routing): give a routed decision only what it can finish reading (#227)
* d34e1dd fix(routing): give the model the material the verifier checks against (#226)
* 25490f6 chore(contracts): sync the vendored route outcome to canonical (#225)
* 8a55d4d fix(routing): pin the task class in the grammar instead of asking for it (#224)
* 1e89ca6 feat(routing): add a second applied route that runs no model (ADR-010 D8) (#223)
* a55c7f3 chore(contracts): sync the vendored route outcome to canonical (ADR-010 D8) (#222)
* 6e9daf2 fix(routing): bound evidence by what verifies, not by how much the model writes (#221)
* 52d7b5f feat(routing): apply a route for real, and move readiness to the routing layer (#220)
* 97afe21 feat(contracts): vendor D6/D7 and stop the swarm claiming a route (#219)
* 741615f chore(contracts): vendor the routing contract's execution correlation (#218)
* f909c4a feat(contracts): vendor canonical contracts and gate them against mqobsidian (#216) (#217)
* 8b2b4a3 feat(telemetry): record the model an execution actually used (#213) (#215)
* bb9a8be feat: mq.execution-outcome.v1 — contract, one truthful emit point, and separate reporting (#206)
* c1b0b4a fix(context): state CodeGraph intentions, never tool names (#212)
* c6b8035 feat(context): read the selection vocabulary from mqobsidian (#211)
* 18888da feat: record how much evidence was grounded, not just pass/fail (#210)
* 7445075 feat: emit feedback-signal.v1 pack-usage records (#209)
* 4b281ef fix: emit plain-text source headers, not HTML comments (#208)
* b3870ff feat: build local notebook packs from mqobsidian's profile (#207)
* d16a5c4 fix: resolve repo-signal from uv tool runtime
* 589b629 docs: sync roadmaps after v1.26.0 and open v1.27.0 (#204)

### Added

* `mq.execution-outcome.v1` — one record per real execution, with routing as a
  field on the record rather than its subject, so route evaluation, skill
  evaluation and tool performance read one contract instead of growing
  separate telemetry formats. `mq.model-route-outcome.v1` is untouched: the
  separation between shadow experiment and production is by contract, so no
  `kind` discriminator was needed and no historical record was migrated.
* Execution instrumentation across every entrypoint: `swarm run`, `audit`,
  `fix-ci`, `docs-audit`, `release-check`, `signal` and `task run`. One
  execution is one operator action and the outermost level owns the record —
  agents are instrumented at the CLI, never in the agent classes, and
  `Executor.run_plan` is not instrumented at all, since it is only ever
  reached from inside an agent. Nesting is therefore impossible by
  construction rather than by convention.
* `route report` and `route history` read both outcome contracts and present
  them in separate tables, under an `execution` key in `--json`, grouped by
  task class and route, with 7-, 30- and 90-day windows and median and p90
  latency. Shadow and execution records are never merged into one rate.
* `route readiness` reports the distance to every eligibility threshold. A
  passing gate yields `AWAITING_OPERATOR_APPROVAL`, never an automatic
  promotion.
* Retention: the outcome file is bounded by size with rotation (10 MiB, three
  prior files), overridable through `MQ_AGENT_OUTCOME_MAX_BYTES`.
* A second applied route that runs no model, so two routes can be compared at
  two levels without the report issuing a verdict.
* Canonical contracts are vendored into the repo and gated against
  `mqobsidian`, including the routing contract's execution correlation and the
  ADR-010 D6/D7/D8 decisions.
* Local notebook packs built from `mqobsidian`'s profile, `feedback-signal.v1`
  pack-usage records, and a selection vocabulary read from `mqobsidian` rather
  than hard-coded.

### Changed

* Telemetry observes a run and never changes it: emission swallows every
  failure, so a broken evidence store costs a record and nothing else, and
  `MQ_AGENT_TELEMETRY=off` disables it entirely.
* A counter the runtime does not measure is absent, not zero — a zero reads as
  "no retries happened" rather than "nobody counted". `tool_calls`, `retries`,
  `fallbacks`, `tokens` and `cost` are therefore optional, and an agent that
  never ran carries no latency at all.
* An outcome record answers "could the run be carried out", not "is the repo
  healthy". An audit that finds problems records `PASS`; a failing task step
  records `FAIL`, because there the runtime could not do what it was asked.
* `--dry-run` on an agent means "make no writes", not "run nothing", so those
  runs record. Only the swarm and task-runner dry runs execute nothing, and
  only those record nothing.
* Routing evidence is bounded by what verifies rather than by how much the
  model writes, the task class is pinned in the grammar instead of being asked
  for, and a routed decision is given only what it can finish reading.
* The local route was given a budget its slow draws can finish inside.
* The planner is told what the tools actually take, and a plan dependency is
  now something the runtime can execute.

### Fixed

* The test suite no longer writes to the operator's evidence store. Three
  tests drive a real `SwarmRunner.run`, so every `pytest` run had been
  appending records indistinguishable from real runs to
  `~/.mq-agent/execution-outcomes.jsonl`. Learned routing is meant to read
  that file, so those were corrupted evidence, not untidiness.
* The execution outcome schema is force-included in the wheel. Without it the
  installed schema path did not exist, emission swallowed the
  `FileNotFoundError`, and every installed runtime recorded nothing while the
  repo's tests stayed green.
* An execution record found in a routing source no longer inflates
  `invalid_records`. It is a valid record of another contract, so it counts as
  neither a valid routing outcome nor an invalid one.
* A run that never started is not a failed execution.
* A runtime that cannot be identified writes no production evidence.
* A model that ran out of time was not unavailable — a generation timeout is
  no longer misclassified.
* The executor rejects a call the tool cannot accept before making it.
* Secret-bearing files are no longer offered to a reader, and a review cannot
  be handed a secret.
* A docs review reads what it planned to read, a review reads what it
  declared, and declared collection integrity is enforced.
* Verifier excerpts are separated from execution completeness.
* Two claims the code did not actually make were withdrawn.
* `repo-signal` resolves from the `uv` tool runtime.
* Source headers are emitted as plain text, not HTML comments, and CodeGraph
  intentions are stated rather than tool names.

## [v1.26.0] — 2026-08-14

* 941368f feat(stack): extend the compatibility gate across the whole stack — Phase 6 (#202)
* 477f270 fix(stack): a repo with no Python dependencies is SKIPPED, not UNAVAILABLE (#201)
* c8ec7ea feat(stack): enforce blocks_release in the release path — Phase 6 (#200)
* ca9116c feat(stack): operator surfaces and CI gates for compatibility — Phase 5 (#199)
* 0cfcd47 feat(stack): fresh resolve for the compatibility gate — Phase 4 (#198)
* 82bccaf ci(tests): type-check tests/ and fix the errors it surfaced (#197)
* 9e6f64b feat(stack): compatibility relationships and range overlap — Phase 3 (#196)
* c9fa38d docs(agents): forbid direct access to the CodeGraph database (#195)
* bbe8536 feat(stack): stack compatibility gate — Phase 0-2 (#194)
* 505ad9f feat(docs): generate the command reference from the Typer app (#193)
* 5331ccc docs: sync roadmaps after v1.25.1 and open v1.26.0 (#192)

### Added

* Generated command reference: `tools/generate_command_reference.py`
  introspects the live Typer app and renders
  `docs/generated/Command-Reference.md`. No hand-maintained command list is
  involved, and the render is deterministic.
* `scripts/publish-wiki-command-ref.sh` projects that one page to the GitHub
  Wiki. Idempotent, diff-driven and warn-only, so a publishing failure never
  invalidates a release.
* CI gate: `tests.yml` fails when the checked-in reference drifts from the
  code.
* `mq-agent stack compatibility` — read-only dependency compatibility gate
  across MQ repositories, implementing Phase 0 (the
  `mq.stack-compatibility.v1` contract) and Phase 1 (repository inventory) of
  the v1.26.0 roadmap. Reports declared and locked versions with per-file
  provenance, flags unbounded ranges and lockfiles outside their declared
  range, and reports missing repos or sources as `UNAVAILABLE` rather than as
  incompatibility. Never modifies dependencies, lockfiles or working trees.
* `schemas/mq_stack_compatibility.schema.json` with stable finding codes and
  an explicit `blocks_release` flag per finding.
* Phase 2 — declared compatibility. `.mq/repo-contract.json` accepts an
  optional `compatibility` block (`protocols`, `dependencies`, `produces`,
  `consumes`). The gate validates it against `pyproject.toml` and separates
  missing metadata (`MQC009`, WARN, non-blocking during rollout) from
  inconsistent metadata (`MQC011`, FAIL) and from a range that contradicts its
  own protocol track (`MQC012`, FAIL).

* Phase 3 — stack relationships. The report's `relationships` array is now
  populated: produced contracts are matched to the repos that consume them,
  and every pair of repos sharing a tracked dependency is assessed for range
  overlap. Ranges that share no version fail as `MQC007`; parallel protocol
  tracks raise `MQC008` (WARN across the stack, FAIL when the two repos are
  wired together through a produced/consumed contract); a consumed contract
  nobody produces raises the new non-blocking `MQC013`. Repos that could not
  be read are skipped rather than treated as incompatible.
* `stack compatibility` prints a Relationships section in human mode, so a
  cross-repo verdict shows the observed ranges on both sides instead of only a
  summary status.

* Phase 4 — fresh resolve. `mq-agent stack compatibility --fresh-resolve`
  answers what a *new* installation would select, which a lockfile can hide
  indefinitely. It compiles the declared ranges with `uv` in a temporary
  directory outside every working tree, records the result as each
  dependency's `resolved` version, and runs the repository's declared critical
  import against that pin. New codes: `MQC015` (WARN — the lockfile masks what
  a fresh install picks), `MQC016` (FAIL — the declared import breaks against
  the resolved version), `MQC017` (FAIL — the declared ranges cannot be
  resolved together) and `MQC014` (UNAVAILABLE — the check could not be run).
* `.mq/repo-contract.json` accepts `compatibility.import_probes`, a map of
  dependency to import statement. Any Python statement works, so a repo can
  smoke its own contract rather than only its imports. Repos that declare
  nothing get `mcp` → `from mcp.server.fastmcp import FastMCP`; declaring an
  empty map opts out.

### Changed

* CI type-checks `tests/` alongside `mq_agent/`. The test suite already had
  four type errors that no gate would have caught; they are fixed and the
  gate now holds the line.
* `schemas/mq_stack_repo_contract.schema.json` gained the optional
  `compatibility` property. Contracts without it stay valid; the schema
  previously set `additionalProperties: false`, so a repo adding the block
  would have been rejected by the contract gate.
* Declare `packaging` explicitly in `dependencies`. It was already imported
  transitively; the compatibility gate parses version specifiers with it.
* `uv.lock` records `packaging` as a direct dependency. It was declared in
  `pyproject.toml` without the lockfile being regenerated — the gate's own
  repo carrying exactly the drift the gate looks for.

### Added (Phase 5)

* Operator surfaces and gates. `mq-agent dashboard` carries a Compatibility row
  and the static verdict in its JSON payload; only a proven `FAIL` counts
  against the dashboard's overall status, since `WARN` is the normal state
  while repos are still declaring their boundary. The stack gate workflow runs
  the static check on pushes to `main` and adds `--fresh-resolve` on the
  nightly schedule and on manual dispatch, where a registry is reachable. Pull
  requests deliberately do not run it: only the checkout exists there, so every
  sibling would report `UNAVAILABLE`.
* `stack compatibility --strict` exits 1 on `WARN`, and an interrupted run
  exits 130 instead of reporting a verdict it never reached.
* `docs/STACK_CONTRACT_GATE.md` documents every status, exit code and finding
  against what it blocks.

### Added (Phase 6)

* `blocks_release` is now enforced by the release path, not only by CI.
  `mq-agent stack release-check` refuses a repository implicated in a proven
  incompatibility, and the release cockpit (`mq-agent ship status|proof|audit`)
  reports `COMPATIBILITY_BLOCKED` with the compatibility command as its next
  action. Both read the static check only — no network, no resolution.
* `release_blockers()` groups blocking findings by every repository they
  implicate. Pairwise findings (`MQC007`, `MQC008`) now carry a `repos` list
  alongside `repo`: naming only the left-hand repo would have blocked one half
  of an incompatible pair and let the other half release.
* Both surfaces treat a compatibility report that could not be produced as
  `UNAVAILABLE` and let the release proceed. Unknown is not incompatible, and a
  gate that cannot run must not refuse every release.
* `release-check --ci` resolves the checkout under test the same way its repo
  entries do, so a pull request is gated on its own single-repo findings
  instead of reporting the repo under test as `UNAVAILABLE`.
* The cockpit reads the repository from the checkout under review, so
  `ship status --repo <worktree>` no longer judges whatever sits in
  `~/<repo>`. `checks.compatibility` is that repository's own verdict; the
  whole-stack status is kept in `checks.evidence.compatibility.stack_status`.
* The gate now discovers which dependencies to assess instead of reading one
  hardcoded name. It tracks every dependency declared by two or more repos —
  the only ones that can disagree across a repository boundary — plus every
  dependency any contract names. `mq-agent`, `repo-signal` and `mqobsidian`
  were previously reported `PASS` having had nothing assessed at all, which is
  a verdict shape for an absence of one; they are now assessed against the
  seven dependencies the stack actually shares.
* Dependencies carry `critical`. Only critical ones — those named in a
  `compatibility` block, plus `mcp` by default — raise `MQC005` (unbounded
  range) and `MQC009` (missing metadata). Nearly every `>=` range in the stack
  is technically unbounded, and warning about all of them would bury the one
  dependency the stack declared as mattering. Discovered dependencies are still
  assessed for proven pairwise incompatibility, which needs no declaration to
  be true. Declaring a boundary in one repo makes that dependency critical
  stack-wide: the exposure lives in whichever repo left its range open.
* `produces` falls back to the contract's existing `contracts` list when no
  `compatibility.produces` is declared. All eight repos already register what
  they produce; requiring a parallel declaration first left the JSON side of
  the gate dead. `mq-ums` and the shell repos now contribute their contracts
  even though their Python status is `SKIPPED`.
* New code `MQC018_CONTRACT_VERSION_SKEW` (FAIL, blocks both repos): a consumer
  still on `X.v1` when the producer has moved to `X.v2`. Previously this
  surfaced as `MQC013_CONTRACT_UNPRODUCED` (WARN), which is the wrong
  diagnosis — the contract exists, it changed underneath its consumer. Unlike
  `MQC013`, a skew is reported even from a narrowed inventory: it needs both
  halves present to be observed, so seeing it is already proof.
* Contract ids match on family and version with separators normalised.
  mq-agent reads mqobsidian's `inbox-manifest.v1` while mqobsidian registers it
  as `inbox_manifest.v1` — matching raw strings reported a correctly wired
  contract as produced by nobody.
* `.mq/repo-contract.json` declares the five mqobsidian export contracts
  `mq_agent/memory/inbox_pipeline.py` reads, so that wiring is now assessed
  rather than assumed.
* Human output collapses the Relationships section to the pairs that disagree,
  with the rest counted on one line. Every pair of repos sharing any dependency
  is a relationship, so the full list is dozens of rows that all say the same
  thing and bury the one that does not. `--json` still carries all of them.
* The `(unbounded)` marker is shown only for critical dependencies — the ones
  the gate actually warns about. Marking every `>=` range implied an action the
  gate does not ask for.
* The MCP incident is preserved as a regression fixture: both repos on the
  FastMCP 1.x track with open ranges, one with no lock and one held green by
  `uv.lock`. The fixture asserts the gate still fails, that the locked repo is
  blocked from releasing, and that the same stack with `<2` actually declared
  passes — the distinction between *works with today's lock* and *declares a
  genuinely compatible future resolution*.

### Fixed

* A repository with no Python dependency source is now `SKIPPED`, not
  `UNAVAILABLE`. `mqlaunch` and `mq-hal` are shell, `mq-ums` is Node; the gate
  reads them successfully and simply has nothing to assess. Calling that "could
  not assess" exited 3 and would have failed the `main` job the moment the two
  MCP repos declared their boundary and their `WARN` — which outranks
  `UNAVAILABLE` — stopped masking it. It also masked the repos whose check
  genuinely did not run. Findings may now carry `SKIPPED` severity.
* A dependency declared with no version at all (`dependencies = ['mcp']`) was
  read as *not declared*: it vanished from the report and the repo came back
  `PASS` with no findings. That is the most exposed declaration there is —
  it admits every future major — and it is the shape of the incident this gate
  exists to catch. An empty specifier is now distinguished from absence and
  raises `MQC005`, plus `MQC012` when a protocol track contradicts it.
* An explicitly requested `--fresh-resolve` that could not run no longer
  collapses into an unrelated `WARN` and exits 0. `UNAVAILABLE` ranks below
  `WARN` in the static ladder, which is right for an unreadable repo and wrong
  for a check the caller asked for; the report now says `UNAVAILABLE` (exit 3)
  unless something actually failed, and `next_action` points at the check that
  did not run.
* An import probe is only `FAIL` when Python ran and the declared statement
  failed. uv failing to build a wheel or reach the registry previously read as
  a broken repository contract, blaming the repo for the machine's problem.
* A fresh resolution targets the repository's own `requires-python` rather than
  the interpreter running the gate. uv reports an unsatisfiable interpreter
  through the same "No solution found" headline as a range conflict, so the
  mismatch was reported as `MQC017` — a release-blocking FAIL against ranges
  that were fine.
* `import_probes` keys are matched by canonical package name, so a contract
  spelling it `MCP` no longer silently skips its own probe.

## [v1.25.1] — 2026-08-10

* f8f14fb fix(ship): audit completed releases as up to date (#190)

## [v1.25.0] — 2026-08-10

* 9fd754f feat(ship): add v1.25 release cockpit (#188)
* 26f21eb chore(skills): make the repo's skills discoverable by Claude Code (#187)
* caa561f fix(types): clear the two mypy errors in the test suite (#186)
* de139d3 feat(memory): expose learn-writeback as its own delegator (#185)
* f80d420 fix(mcp): tell an unreachable server apart from a missing tool (#184)
* adf6926 feat(routing): expose per-decision routing history (#183)
* e24f23a feat(routing): make local-first routing evidence mean something (#182)
* 6b46a4e feat(routing): add evidence promotion review (#181)
* eb87ca5 feat(routing): add advisory shadow routing commands (#179)
* 03b6a7f feat(routing): define versioned model routing contracts (#178)
* a343494 fix(context): consume blocker declarations (#177)
* aa94e0b fix(run-tool): exit non-zero when the tool did not succeed (#176)
* 9e4ced7 fix(codegraph): consume MCP-native task guidance (#175)
* 7ad89ce fix(stack): clarify repository product-readiness sweep (#174)

## [v1.24.1] — 2026-07-23

* fa38d5f fix(ci): align Ruff check with repository default rules (#172)
* bc41b25 fix(ci): include mqobsidian in stack gate checkout (#171)
* acee4a8 fix(stack): stabilize post-v1.24 release planning (#170)

## [v1.24.0] — 2026-07-22

* e593d73 fix(stack): route single-repo releases by contract (#169)
* 3c90a0f fix(release): sync docs during prepare (#167)
* 9e9db86 docs(release): plan mq-agent v1.24.0 (#166)
* 1bcaf40 feat(stack): route protected releases through pull requests (#165)
* 7c2c185 fix(stack): block missing repo contracts and validate release_mode (#164)
* f5232ec docs(readme): update current release direction (#163)
* 6629b5e docs(release): sync v1.23 status surfaces (#162)
* 71068d4 feat(models): harden Ollama runtime diagnostics (#161)
* 9d92a60 feat(stack): close the release_mode value set and name what each one means (#160)
* ff72b2e fix(release): re-gate on the repo's own release-check after the bump (#159)
* cc9ae84 docs(roadmap): record the release-mode gap and what v1.23.0 taught (#158)
* 2a6800c feat(stack): make branch protection a release contract, not a push error (#157)

### Added

* `mq-agent models doctor [--json]` — read-only Ollama runtime diagnostics for
  version, installed/loaded models, profile resolution, mq-learn Modelfile
  drift, and a structured JSON smoke test.
* `mq-agent models bench` now reports load/total duration, prompt/output token
  counts, tokens per second, and JSON/schema validity through
  `ollama_model_benchmark.v1`.

### Changed

* Default `fast`, `review`, and `planner` profiles now use the installed exact
  model name `qwen3:4b-instruct` instead of the unresolved `qwen3` alias.
* Model benchmarks now use Ollama's local generate API with `keep_alive=0` by
  default; `--keep-alive` can override that runtime setting.
* Runtime policy keeps `qwen3:4b-instruct` for general fast/planner/review work,
  `mq-learn` for structured extraction, `bakllava` for vision only, and
  `llama3.2` as an unprofiled fallback. Vector storage and deep learn variants
  remain gated on measured retrieval and context-window needs.

## [v1.23.0] — 2026-07-19

* e59e8e4 fix(release): sync uv.lock version so a release cannot ship its own drift (#155)
* b527694 feat(stack): multi-repo release execute behind --execute --approve (#154)
* 5c351b6 docs(roadmap): v1.23.0 checkpoint — 4/5 slices done, execute deferred (#153)
* 269430b docs(roadmap): close tag disposition — known-bad kept, fixed forward (#152)
* f5433c3 docs(roadmap): mark release-check.sh rollout done (3/8 -> 8/8) (#151)
* 3eb620b fix(stack): raise preflight release-check timeout 120s -> 300s (#150)
* b89de0b docs(roadmap): mark agent-context-pipeline prepare steps done (#149)
* e3867f9 docs(roadmap): reconcile v1.23.0 state (converge done, rollout 3/8) (#148)
* 6098088 feat(release): make release-check.sh conform to repo_release_check.v1 (#147)
* 700d7dc feat(stack): read-only multi-repo release preflight hook (#146)
* ad68beb docs(stack): lock multi-repo execute design (--all --execute) (#145)
* f84faf6 feat(stack): re-verify on-main and clean tree before executing a release (#144)
* e37b702 feat(stack): refuse a release plan when the target tag already exists (#143)
* b253e57 chore(lint): enforce markdown consistency in CI (#142)
* bbc6111 feat(stack): plan a release for the whole stack at once (#141)
* dc8ab48 docs(roadmap): reframe v1.23.0 around release-path convergence (#140)
* 966cc66 docs(workflow): add fence language to WORKFLOW_CONTRACT code blocks (#139)

### Changed

* The multi-repo preflight's per-repo `release-check.sh` timeout is raised from
  120s to 300s. Repos with heavy dependencies (ML imports) running their full
  suite legitimately exceed a minute on a cold cache; the tighter limit reported
  them as timeout-BLOCKED false positives.
* `release-check.sh` now conforms to the `repo_release_check.v1` contract:
  `--json` emits the machine-readable object (`schema`, `repo`, `status`,
  `blockers`, `warnings`, `evidence`) on stdout and exits 0; `--dry-run` is
  accepted (the check is already read-only). Human mode is unchanged. mq-agent
  is the first repo to satisfy the multi-repo preflight's release-check gate.

### Added

* `mq-agent stack release --all --execute --approve` — multi-repo release,
  completing v1.23.0. `execute_stack_release_all` runs the read-only preflight,
  fail-fast gates on any `BLOCKED` repo before a single mutation, then releases
  the `READY` repos in explicit `MQ_STACK_REPOS` (dependency) order with
  stop-on-first-failure. Repos after a failure are reported `SKIPPED` and never
  started. An already-released repo is left released — un-releasing it would
  mean deleting a pushed tag or rewriting history, so repair is fix-forward.
  `--execute` without `--approve` prints what would be released and touches
  nothing (exit 1). Reported via `mq_stack_release_all_execute.v1` with
  `released_count`, `failed_count`, `skipped_count`, and `aborted_phase`.
* `plan_stack_release` now refuses a target version whose tag already exists
  (locally or on `origin`), so `stack release` cannot re-cut an existing tag.
  Without it, `execute` built the release commit and only then aborted at the
  tag step, leaving a dangling commit — the drift shape v1.23.0 targets.
* `execute_stack_release` re-verifies the on-main and clean-tree preconditions
  against the live repo before any mutation, so a plan built on main cannot
  release once the checkout has moved to a feature branch or gone dirty. It
  aborts with a clear reason, creating no commit, tag, or push.
* `stack release --all --preflight` — read-only multi-repo release preflight
  (`preflight_stack_release_all`, schema `mq_stack_release_all_execute.v1`). The
  strict fail-fast refusal surface: dirty, off-main, unpushed commits, target
  tag exists, `VERSION`/contract mismatch, and each repo's read-only
  `release-check.sh --dry-run --json` (`repo_release_check.v1`) verdict. Never
  mutates and never executes; exits 1 if any repo is blocked. First slice of the
  multi-repo execute design (`docs/STACK_RELEASE_ALL_EXECUTE.md`).

## [v1.22.0] — 2026-07-17

### Added

* `mq-agent obsidian inbox list|read|rank` — the promotion inbox surface
  `mqlaunch` delegates to, read from mqobsidian's canonical exports through the
  single `truth-export-index.json` entrypoint. No raw-vault fallback; reads fail
  closed on stale, missing, or drifted truth.
* `mq-agent obsidian promote|reject|defer|rollback|deprecate` — five explicit
  transition verbs, never a generic passthrough. Preview by default; `--confirm`
  applies. Writes are delegated to mqobsidian, which owns the state machine.
* `schemas/inbox_promotion_orchestration.v1.json` — the ranked-inbox contract,
  registered in `.mq/repo-contract.json`. Policy weights and thresholds are
  mqobsidian data; the formula and bucket routing are mq-agent code. Nothing is
  hardcoded here.

### Notes

* v1.22 Task 8 (generalized evidence adapters) is **blocked by producer
  contracts**, not deferred — see mqobsidian DEC-004. `mq-mcp review_file`
  returns prose rather than JSON, and `repo-signal` declares
  `readiness_score.v1` / `publish_checklist.v1` while emitting neither, so an
  adapter could only be tested against invented fixtures. The working evidence
  path (`run_cochange` → `memory-observation.v1`) is unaffected.

## [v1.21.0] — 2026-07-16

Covers the v1.19.0 operator dashboard, v1.20.0 autonomous stack, and v1.21.0
mq-hal operator readiness milestones, which were implemented but never
released — the package stayed on 1.18.0 while the roadmap moved to v1.21.

### Added

#### Operator contracts (v1.21.0)

* Stable additive JSON Schemas for the five mq-hal operator read surfaces.
* Approved stack-loop executions append compact `mq_stack_loop_audit.v1`
  records for read-only display by mq-hal.
* `mq_hal_operator_contract.v1` in the repo contract, plus the documented
  `mq-agent → mq-hal` read contract and `next_action` section.

#### Operator dashboard and autonomous stack (v1.19.0, v1.20.0)

* `mq-agent dashboard` — read-only snapshot of stack health, release, brain,
  Ollama, repos and contracts, with refresh-oriented TUI panels.
* `mq-agent stack loop` — controlled planning and approved one-step execution
  with command-specific rollback.
* `next-action` contract propagated through cockpit and dashboard.

#### Workflow engine

* `workflow-plan.v1` contract, local workflow state and storage, three fixed
  templates and a workflow CLI.
* Read-only runner with conditions, result normalization, policy-based gates,
  and limited adaptive planning.
* `workflow-observation.v1` emitted after runs.

#### Co-change memory loop

* `memory-observation.v1` co-change observation emitter.
* `mq-agent memory inbox-cochange` — operator-triggered co-change inbox
  pipeline, with the cluster floor separated from the emission floor.
* Explicit review/resolution surface for the memory loop.

#### Context and agent surfaces

* Task-specific context packs (`mq-agent context pack`), Phase 11 exclusions
  and block metadata, and concrete CodeGraph queries.
* Repo-local context snapshot export.
* Published mq-agent agent entrypoints and compressed agent-view cards, with a
  drift-check guard and per-system rebuild triggers.

#### mqobsidian inbox (v1.22.0 groundwork)

* Read-only reads of canonical mqobsidian inbox exports through the single
  `exports/truth-export-index.json` entrypoint.

#### Skills

* `stack-operations` skill — owns the stack suite (sweep, report, alert,
  history, cockpit, gates, release pipeline, loop, brain-gate, truth-export)
  and the `.mq/repo-contract.json` contract rules; the surface had no skill
  owner since v1.6.
* `scripts/check-skills.sh` — validates skill frontmatter, cross-references,
  referenced paths, and the generated SKILLS.md table; wired into
  `release-check.sh`. `--fix` regenerates the table.
* `mq-agent stack skills-check` — cross-repo skill consistency gate. Runs each
  stack repo's `scripts/check-skills.sh`; DRIFT/BLOCKED fail the gate, REVIEW
  (skills without a validator) does not. Supports `--json` and `--ci`. New
  `skills_gate.v1` contract.
* Evals and When to use / When not to use sections in every skill.

### Changed

* `release-readiness` skill rebuilt around the actual gates: `release-check.sh`,
  `mq-agent stack contract-check`, `stack release-notes`, and the orchestrated
  `stack release` pipeline.
* SKILLS.md converted to the stack-standard generated table format; the stale
  "future `mq-agent review`" claim replaced with the shipped
  `mq-agent review file/diff/repo` commands.
* `mq-agent learn` and `review` forward the repo path for cross-repo review and
  learn extraction.

### Fixed

* Stack-loop tests no longer write real audit records into the operator's
  `~/.mq-agent/stack-loop-history.jsonl`. The test ran an approved execution
  without isolating `MQ_AGENT_STATE_DIR`, so every suite run appended a
  fabricated `stack-release` entry that `mq-hal history` rendered as a genuine
  release.
* Co-change resolves the repo correctly for relative target paths.
* The workflow runner injects `repo_name` so `run_tests` resolves.
* Review forwards the repo path through the bridge to mq-mcp `review_repo`.

## [v1.18.0] — 2026-06-12

### Added

* `mq-agent memory ingest` — read-only mqobsidian Markdown index across truth,
  reviews, learn, releases, architecture, decisions and stack runs.
* `mq-agent memory query` / `memory search-vault` — local vault search without
  requiring mq-mcp or a vector store.
* `mq-agent memory summarize` — section-level memory summary with note counts,
  word counts and top tags.
* `mq-agent memory link` — read-only link candidates between related notes.
* `memory_engine.v1` repo contract capability and `docs/MEMORY_ENGINE.md`.

### Changed

* Write-backed vault links are deferred to a later explicit approval flow;
  v1.18.0 keeps the memory engine read-only.

## [v1.17.0] — 2026-06-12

### Added

* `mq-agent models` — first-class Ollama runtime surface with `list`,
  `current`, `switch`, and `bench`.
* `~/.mq-agent/models.json` model profiles for `fast`, `review`, `planner`,
  and `memory`; `models switch` requires `--approve` before writing config.
* `mq-agent stack run` now includes the active model profile in the Ollama
  runtime check payload.

## [v1.16.0] — 2026-06-11

### Added

* `mq-agent stack run` — v1.16 stack runtime gate for repo-signal, mq-mcp,
  Ollama, brain export rendering and release readiness. Read-only by default;
  supports `--dry-run`, `--json`, `--markdown`, `--brain`, `--ci`, and
  `--approve`.
* `mq-agent run --stack` — canonical root alias for the stack runtime pipeline.
* `docs/MQ_CONTROL_PLANE.md` — system map for signal, review, learn, memory
  and release across the MQ stack.

## [v1.15.0] — 2026-06-11

### Fixed

* `mq-agent signal --brain --dry-run` no longer writes to the brain — the
  brain note is skipped on dry-run, per the flag contract.

### Added

* Flag contract enforced across write-capable commands: `--dry-run` never
  writes, `--json` is machine-readable, `--brain` respects `--dry-run`,
  `--approve` is required for primary-write commands. Structural rules are
  locked by `tests/test_flag_contract.py` (Typer introspection: every
  `--brain` command must offer `--dry-run` and `--json`).
* `mq-agent learn extract-review --dry-run` / `learn review-flow --dry-run` —
  preview the mq-mcp calls (and the would-be brain write) without executing.
* `mq-agent decide` now requires `--approve` (Class C write to
  mqobsidian/decisions/), matching `brain record-review`.
* `mq-agent brain record-review --json` — machine-readable result.
* Stack cockpit — `mq-agent stack cockpit` merges git state, contract gate,
  release gate, unreleased work and mqobsidian truth-note freshness into one
  read-only table with a recommended next action per repo
  (`mq_agent/tools/stack_cockpit.py`, registered as the `stack_cockpit` tool).
  Later the input to mq-hal. `--json` for a machine-readable snapshot.
* `docs/STACK_COCKPIT.md` — reference documentation.
* `docs/COMMAND_SURFACE.md` — added the missing `stack release` section and
  the new `stack cockpit` section.
* 17 new tests (`tests/test_stack_cockpit.py`).
* Standard mqobsidian export structure — `mq-agent brain structure` checks
  the vault against the standard layout (`memory/stack-truth/`,
  `memory/reviews/`, `memory/learn/`, `mq-stack/runs/`, `mq-stack/roadmaps/`),
  reports legacy vault-root directories, and creates the missing directories
  with `--init --approve` (`mq_agent/tools/vault_structure.py`, registered as
  the `vault_structure` tool). Gate-friendly exit codes; `--json` output.
* `docs/VAULT_STRUCTURE.md` — reference documentation; Brain Commands section
  in `docs/COMMAND_SURFACE.md`.
* 15 new tests (`tests/test_vault_structure.py`).
* Brain release gate — `mq-agent stack brain-gate` runs the pre-release
  checklist for the brain-integrated stack: contract-check READY,
  release-check GO, truth-export dry-run renders, vault structure complete,
  and the review→brain write path wired (mq-mcp reachable with both
  `review_repo` and `brain_record_review`). Read-only, gate-friendly exit
  codes, `--json`
  (`mq_agent/tools/brain_gate.py`, registered as the `brain_release_gate`
  tool).
* `docs/BRAIN_GATE.md` — reference documentation.
* 12 new tests (`tests/test_brain_gate.py`).

## [v1.14.0] — 2026-06-11

### Added

* Stack release orchestration — `mq-agent stack release --repo <name>` runs a
  gated single-repo release pipeline: release-check pre-gate, version bump
  (`--bump patch|minor|major` or explicit `--version`), contract sync,
  changelog section drafted from commits since the last tag, release commit,
  tag, push, and a closing stack truth-export to mqobsidian
  (`mq_agent/tools/stack_release.py`, registered as the `stack_release` tool).
* Dry-run by default — `--execute` applies the plan; any failed step aborts
  the run and pre-commit file edits are rolled back, so no repo is left
  half-released. `--json` for machine-readable output and CI exit codes.
* `docs/STACK_RELEASE.md` — reference documentation.
* 27 new tests (`tests/test_stack_release.py`).

## [v1.13.0] — 2026-06-11

### Added

* Stack truth export — `stack export` upgraded from a status table to a durable
  truth snapshot combining contract-check and release-check, written as a dated
  Markdown note to mqobsidian (`mq_agent/tools/stack_truth.py`, registered as
  the `stack_truth_export` tool).
* `mq-agent stack truth-export` — primary name for the stack truth export;
  `stack export` is kept as a backwards-compatible alias.
* `docs/STACK_TRUTH_EXPORT.md` — reference documentation.
* `mq-agent stack contract-check --ci` / `stack release-check --ci` — CI mode:
  sibling repos missing from the workspace are reported as SKIPPED instead of
  failing the gate; the CI checkout itself is detected via its directory name
  and fully validated.
* `_ci_repo_path()` helper in `stack_tools.py`.
* `mode` field (`ci` / `local`) in the JSON output of both gates.
* 21 new tests (`tests/test_stack_ci_mode.py`).

### Fixed

* `stack truth-export` / `stack export` now defaults to the dated note path
  (`~/mqobsidian/memory/stack-truth/YYYY-MM-DD-mq-stack-truth.md`) as documented;
  previously the CLI always passed the old `05_RELEASE_STATUS.md` path.

### Changed

* `.github/workflows/mq-stack-gate.yml` split into two jobs: `pr-gate` runs the
  fast `--ci` gates on pull requests (isolated from sibling-repo drift);
  `full-stack-gate` keeps the multi-repo checkout for pushes to `main`, a
  nightly cron run, and manual dispatch.
* `stack contract-check` status model extended with SKIPPED (CI mode only).

## [v1.12.0] — 2026-06-10

### Added

* `.github/workflows/mq-stack-gate.yml` — GitHub Actions workflow for MQ stack gates.
* CI checks out the active MQ stack repos into one workspace.
* CI links the checked-out repos into the `~/...` layout expected by `MQ_STACK_REPOS`.
* `mq-agent stack contract-check --json` now runs on pull requests and pushes to `main`.
* `mq-agent stack release-check --json` now runs on pull requests and pushes to `main`.
* `.mq/repo-contract.json` now declares `ci_stack_gate.v1` for mq-agent.

### Changed

* Version bumped to `1.12.0` in `VERSION`, `pyproject.toml`, README badge and repo contract.
* Roadmap marks v1.12.0 as complete and sets v1.13.0 as mqobsidian stack truth export.

## [v1.11.0] — 2026-06-10

### Added

* `mq-agent stack contract-check` — validates `.mq/repo-contract.json` manifests across MQ stack repos.
* `mq-agent stack contract-check --json` — machine-readable output.
* `_contract_entry()` helper in `stack_tools.py` — READY / REVIEW / DRIFT / BLOCKED per repo.
* `REQUIRED_CONTRACT_FIELDS` constant in `stack_tools.py`.
* `schemas/mq_stack_repo_contract.schema.json` — JSON Schema for repo contract manifests.
* `.mq/repo-contract.json` in all active MQ stack repos.
* `docs/STACK_CONTRACT_GATE.md` — reference documentation.

## [v1.10.0] — 2026-06-10

### Added

* `mq-agent stack release-notes` — draft release notes from git commits since last tag.
* `mq-agent stack release-notes --repo <name>` — single repo filter.
* `mq-agent stack release-notes --json` — machine-readable output.
* `docs/STACK_RELEASE_NOTES.md` — reference documentation.

## [v1.9.0] — 2026-06-10

### Added

* `mq-agent stack report` — consolidated per-repo score, trend, alert and readiness view.
* `mq-agent stack release-check` — local release gate across all stack repos.
* JSON output for stack report and release gate.
* `docs/STACK_REPORT.md` — reference documentation.

## [v1.8.0] — 2026-06-10

### Added

* `mq-agent stack alert` — threshold-based regression detection.
* `mq-agent stack sweep --alert` — inline alert at end of sweep.
* Configurable `--threshold`, `--min-score` and JSON output.
* `docs/STACK_ALERT.md` — reference documentation.

## [v1.7.0] — 2026-06-10

### Added

* Stack sweep history persisted to `~/.mq-agent/sweep-history.jsonl`.
* `mq-agent stack history` — trend table across past sweeps.
* `mq-agent stack history --diff` and `--json`.
* `docs/STACK_HISTORY.md` — reference documentation.

## [v1.6.0] — 2026-06-10

### Added

* `mq-agent stack sweep` — run repo-signal over every MQ stack repo.
* `--brain`, `--decide`, `--dry-run` and `--json` modes for stack sweep.
* mqlaunch agent menu item 18 — stack health sweep.
* `docs/STACK_HEALTH.md` — reference documentation.

## [v1.5.0] — 2026-06-10

### Added

* End-to-end MQ stack demo flow: signal → review → release-check.
* mqlaunch demo-flow command and menu integration.
* `docs/DEMO.md` rewritten as canonical walkthrough.

## [v1.4.0] — 2026-06-04

### Added

* mq-image-analyze MCP endpoint registration.
* Visual architecture context in review commands via `--architecture-image` / `--visual`.
* Read-only safety classification for visual perception tool families.

## [v1.3.0] — 2026-05-31

### Added

* Architecture-memory context surfaced after review findings.
* `--fast` review mode routing through mq-mcp Class A policy.
* Learn status/search/explain commands.
* Optional bridge helpers for architecture decisions and learned patterns.

## [v1.2.0] — 2026-05-31

### Added

* Semantic memory search/store commands.
* MCP status enrichment with semantic memory and orchestration contract checks.
* Docs and examples for semantic memory workflows.

## [v1.1.0] — 2026-05-31

### Added

* Review file/diff/repo orchestration through mq-mcp.
* Security, architecture and risk flags forwarded to mq-mcp review contracts.
* Dry-run support for review commands.
* Orchestration contract validation in `mq-agent doctor`.

## [v1.0.0] — 2026-05-26

### Added

* Stable orchestration platform release.
* Rich CLI rendering helpers and diagnostics module extracted from `main.py`.
* Configuration-driven model selection.
* Full architecture, examples and safety documentation.

## [v0.9.0] — 2026-05-26

### Added

* Orchestration contract suite for PlanStep, StepResult, AgentManifest, AgentState and tool registry.
* `MqAgentConfig` config model with environment override support.
* Runtime boundary documentation for Executor loop and SwarmRunner.

## [v0.8.0] — 2026-05-24

### Added

* Controlled swarm orchestration: list, plan, run, audit and release-check.
* Browser-safe URL inspection and release verification workflows.
* Declarative swarm audit task workflow.

## [v0.7.0] — 2026-05-24

### Added

* Browser inspection, summarization and release verification commands.
* Browser tool registry integration and URL safety gates.

## [v0.6.0] — 2026-05-24

### Added

* Declarative YAML task runner.
* `mq-agent task list` and `mq-agent task run` with dry-run and JSON output.

## [v0.5.2] — 2026-05-24

### Added

* `mq-agent mcp start`, `mq-agent mcp stop` and background process management.
* PID-file based mq-mcp lifecycle helpers.

## [v0.5.1] — 2026-05-24

### Added

* Memory doctor diagnostics and JSON output.
* Semantic memory status hardening and docs updates.

## [v0.5.0] — 2026-05-24

### Added

* Semantic repository memory via repo-signal.
* Memory build/refresh commands with explicit approval gates.

## [v0.4.1] — 2026-05-23

### Added

* Command surface documentation and docs consistency checks.
* `mq-agent docs-audit` command.
* Model override environment variables.

## [v0.4.0] — 2026-05-23

### Added

* mqlaunch integration and direct prompt command surface.
* `scripts/smoke-mqlaunch.sh` and bridge documentation.

## [v0.3.0] — 2026-05-23

### Added

* Local MCP tool orchestration layer.
* MCP status, MCP tools, tool description and run-tool commands.
* Tool safety classification model.

## [v0.2.4] — 2026-05-23

### Added

* Release hygiene and docs consistency checks.
* Release-check gate and documentation hardening.

## [v0.2.3] — 2026-05-23

### Added

* Proof section and install smoke test.
* GitHub Actions install smoke workflow.

## [v0.2.2] — 2026-05-23

### Added

* Demo polish, command docs, safety contract and MQ ecosystem docs.
* Skills directory and release-readiness examples.

## [v0.2.0] — 2026-05-23

### Added

* repo-signal integration.
* README scoring, publish checklist and signal commands.

## [v0.1.0] — 2026-05-23

### Added

* Core orchestration layer: Planner, Executor, Verifier, Memory and SafetyGate.
* Git, shell, repo and MCP bridge tools.
* Initial Typer CLI, Textual TUI and GitHub Actions CI.
