# MCP Tool Contract Checking Implementation Plan

## Goal

Make the stack compatibility gate report when mq-agent depends on an MCP tool
whose name, safety class or input schema no longer matches what its producer
declares. It reads committed, declared files, as every other compatibility check
does.

## Owner repo

mq-agent: the checker, the consumer manifest and the MQC codes.

## Secondary repos

- mq-mcp: producer of the tool surface artifact and its schema.
- mq-image-analyze: second producer (Phase 3).
- mq-hal / macos-scripts: read-only surfaces. These are not in this plan, and
  they may not reimplement the assessment.

## Architecture boundary

- mq-mcp owns its tools, their safety classes (ADR-003, A–D) and the
  published description of them. The checker never redefines a class.
- mq-agent owns the comparison, its findings and their release consequences
  (`stack_compatibility.py`, `schemas/mq_stack_compatibility.schema.json`).
- The comparison reads declared files from both repos. A live server is
  optional evidence (Task 9), never the source of truth: a stopped server is
  `UNAVAILABLE`, not incompatible.
- mqobsidian owns cross-repo memory contracts. The tool surface is runtime
  truth that mq-mcp owns, so its schema lives in mq-mcp, next to
  `docs/tool_contracts.json` and the declared `tool_registry.v1`.
- This plan proposes behavior. Writing it changes no gate.

## Why now

ROADMAP "Deferred — MCP tool contract checking" is the only compatibility
check deferred from v1.26.0 that mq-agent owns. The other checks read declared
files. This one was deferred because the facts it needs lived only in mq-mcp's
live registry. Task 1 below removes that obstacle. Learned routing is
waiting on evidence that accrues by calendar time, so this work does not compete
with it.

## Verified facts — 2026-10-14

Measured read-only against a running mq-mcp (`/runtime-identity`: 2.1.0,
commit `8d7d70b`) and mq-mcp `origin/main` (`e637926`).

**Producer, mq-mcp:**

- `docs/tool_contracts.json` declares 137 tools: 46 A, 37 B, 22 C, 32 D.
  Each entry has `name`, `class`, `write`, `subprocess`, `side_effects`,
  `resolver`, `description` and `examples`. It has **no input schema**.
- `scripts/check-tool-contracts.sh` checks that every `@mcp.tool` in
  `server.py` appears in the contract file. It compares **names only**, and it
  finds them with `grep`, not from the registry.
- `GET /tools` returns the FastMCP registry, which includes `inputSchema` for all
  137 tools. `_enrich_tool` adds `safety_class` from the contract map.
  `annotations` (MCP `readOnlyHint` and similar) is empty on all 137 tools.
- `.mq/repo-contract.json` declares `tool_registry.v1` and `safety_class.v1`
  under `contracts`. `compatibility.produces` declares nothing. The ROADMAP
  example `mq-mcp.tools.v1` exists in no repo.
- The running server (`8d7d70b`) is behind main (`e637926`). Its `review_repo`
  lacks the `structured` parameter that main has. A live-only check would
  have judged the stale process, not the code.

**Consumer, mq-agent:**

- 26 distinct tool names are referenced by literal: `call_tool(...)`,
  `call_tool_if_available(...)`, `describe_tool(...)` and the
  `"tool"` field in `mq_agent/workflows/templates/*.json`.
- 2 of them are not registered in mq-mcp: `image_perception` and
  `observe_architecture`. `_infer_default_tool_source` attributes the
  `observe_` family to mq-image-analyze, so this is a second producer, not
  drift. Phase 3 covers it.
- `mq-agent mcp run` gates on `MCPToolSpec.safety_class`
  (`main.py`, `mcp run`). Unknown blocks. C/D need `--approve`, and dangerous
  needs `--dangerous`.
- When server metadata is missing, the class is **guessed from the name
  prefix** (`classify_tool_name`). Against the declared classes:
  - 74 of 137 tools cannot be classified by name.
  - 6 disagree with the declared class. `extract_coding_conventions` is
    declared C (write) but guessed read-only. That under-classification would
    run a write tool without `--approve`. `set_volume`, `create_note`,
    `set_reminder` and `set_wallpaper` are declared D but guessed C, which
    takes the same `--approve` gate. `validate_orchestration_contract` is
    declared A/B but guessed subprocess, an over-classification that is safe.
- `normalize_safety_class` maps A/B to read-only, C to write-capable and D to
  subprocess. This matches ADR-003 ("A/B are safe to auto-approve").
- `_tool_supports_input` already reads `input_schema` to opt into
  `review_repo(structured=...)` only when advertised. That consumer-side
  tolerance is the pattern for optional parameters.

## Non-goals

- No change to any tool's safety class or to ADR-003.
- No live-server dependency in CI or in the release gate.
- No reimplementation of the assessment in mq-hal or mqlaunch.
- No MCP `annotations` (`readOnlyHint`, `destructiveHint`) in this plan. Deriving
  them from the class in mq-mcp is a separate, reasonable follow-up.
- No contract for tool *output* shape. `outputSchema` exists in FastMCP but no
  consumer here reads it yet.

## Design

### Producer artifact: `mq-mcp.tool-surface.v1`

A committed, generated file in mq-mcp, `contracts/tool_surface.v1.json`:

```json
{
  "schema": "mq-mcp.tool-surface.v1",
  "producer": "mq-mcp",
  "tool_count": 137,
  "tools": [
    {
      "name": "review_repo",
      "safety_class": "B",
      "write": false,
      "subprocess": false,
      "parameters": [
        {"name": "max_files", "type": "integer", "required": false},
        {"name": "structured", "type": "boolean", "required": false}
      ],
      "signature_sha256": "…"
    }
  ]
}
```

- It is generated in-process from `mcp.list_tools()` and the contract map. It is
  not built by `grep` and not by HTTP, so it describes exactly the registered
  tools.
- `parameters` carries only `name`, JSON type and `required`. Descriptions and
  defaults are excluded, so the file changes when the call contract changes and
  not when prose changes.
- `signature_sha256` hashes the canonical JSON of `parameters`. It makes a
  change visible at a glance. Findings still name the concrete parameter.
- mq-mcp CI regenerates the file and diffs it, as mqobsidian does for its
  context exports. A tool added without regenerating fails mq-mcp's own CI.

### Consumer manifest: `.mq/mcp-tool-requirements.json` in mq-agent

```json
{
  "schema": "mq-agent.mcp-tool-requirements.v1",
  "tools": [
    {"name": "review_repo", "producer": "mq-mcp",
     "max_safety_class": "B",
     "arguments": ["repo_path", "mode", "max_files", "receipt"],
     "optional_arguments": ["structured"]}
  ]
}
```

- `max_safety_class` is the highest class the calling flow is written to
  accept. If the producer raises the class above it, the finding is a release
  blocker.
- `arguments` must exist in the producer's parameters. `optional_arguments` are
  sent only after a capability probe such as `_tool_supports_input`, so their
  absence is a WARN, not a FAIL.
- A test keeps the manifest honest. Every literal tool reference in
  `mq_agent/` and in the workflow templates must be listed, and every listed
  tool must still be referenced. A hand-written list with no test would drift,
  which is the defect `core/tool_contract.py` already warns about one level
  down.

### New MQC codes (append-only, v1)

| Code | Status | When |
| --- | --- | --- |
| `MQC019_TOOL_NOT_PRODUCED` | FAIL | a required tool is absent from its producer's surface |
| `MQC020_TOOL_SAFETY_ESCALATED` | FAIL | the producer class is above the consumer's `max_safety_class` |
| `MQC021_TOOL_ARGUMENT_UNDECLARED` | FAIL / WARN | a sent argument is not a producer parameter (WARN when optional) |
| `MQC022_TOOL_REQUIRED_ARGUMENT_UNSENT` | FAIL | the producer requires a parameter the consumer never sends |
| `MQC023_TOOL_SURFACE_UNAVAILABLE` | UNAVAILABLE | the producer has no surface artifact, or it is invalid |
| `MQC024_TOOL_SURFACE_LIVE_DRIFT` | WARN | `--live` only: the running server differs from the committed surface |

These follow the v1.26 rules:

- Unknown is not incompatible. A missing artifact is `UNAVAILABLE` and blocks
  nothing during rollout.
- Pairwise findings carry `repos: [consumer, producer]`. Gating reads
  `release_blockers()`, never `finding["repo"]`.
- A WARN source that is fixed can uncover an `UNAVAILABLE` beneath it, so check
  the exit code, not just the status (the masking trap from 2026-08-13).

## Approval gates

- Before file writes: yes. Each phase starts only on operator approval.
- Before commit: yes.
- Before push/PR: yes.
- Before merge: always the operator.
- Before deletion/settings changes: yes. No branch-protection change is planned.

## Test gates

mq-mcp:

```bash
uv run pytest -q
./scripts/check-tool-contracts.sh
uv run python scripts/export_tool_surface.py --check
```

mq-agent:

```bash
uv run pytest -q
./release-check.sh
uv run mq-agent stack compatibility --json
uv run mq-agent stack contract-check
```

## Rollback

- Every task is one squash PR, and `git revert` is enough.
- Exception: once a release publishes MQC019–MQC024, the enum values stay
  (append-only in v1). A rollback removes the producing code, not the enum.
- The producer artifact is additive in mq-mcp. Reverting it makes the mq-agent
  check return `MQC023` (UNAVAILABLE), which blocks nothing.

## Tasks

### Phase 1 — mq-mcp publishes its tool surface

### Task 1: Tool surface schema

**Purpose:** a contract to validate the artifact against, owned by the producer.

**Files:**

- Create: `contracts/tool_surface.v1.schema.json` (mq-mcp)
- Modify: `.mq/repo-contract.json`: add `mq-mcp.tool-surface.v1` to
  `contracts` and to `compatibility.produces`
- Read-only reference: `contracts/release_gate_v2.schema.json` (style)

**Steps:**

1. Write positive/negative schema tests first: unknown class, missing
   `parameters`, extra field.
2. Write the schema with `additionalProperties: false` and the class enum A–D.
3. Run the gates and summarize the diff.

**Expected result:** the tests pass, and an invalid example is rejected.

**Commit suggestion:** `feat(contracts): add mq-mcp.tool-surface.v1 schema`

### Task 2: Generate the surface from the registry

**Purpose:** publish what is actually registered, not what grep finds.

**Files:**

- Create: `scripts/export_tool_surface.py` (mq-mcp), `contracts/tool_surface.v1.json`
- Create: `tests/test_tool_surface_export.py`
- Read-only reference: `mq-mcp/server.py` (`_SAFETY_MAP`, `_enrich_tool`),
  `mq-mcp/tool_registry.py`

**Steps:**

1. Tests first:
   - output validates against Task 1's schema;
   - every registered tool appears exactly once;
   - parameter order is deterministic;
   - descriptions do not affect `signature_sha256`.
2. Implement with `await mcp.list_tools()` in-process. Map `inputSchema`
   to `parameters` (name, type, required). Join the class from the contract map.
   A tool with no class fails the export instead of writing `unknown`.
3. `--check` regenerates in memory and exits non-zero on a diff.

**Expected result:** a committed artifact with 137 entries. `--check` is
clean.

**Commit suggestion:** `feat(contracts): publish the registered tool surface`

### Task 3: Keep the surface fresh in mq-mcp CI

**Purpose:** a tool or parameter change without regeneration fails where it is
made.

**Files:**

- Modify: the mq-mcp test workflow (add `export_tool_surface.py --check`),
  `scripts/check-tool-contracts.sh` (call it, so the local gate covers it as well)

**Expected result:** CI goes red on a deliberately stale artifact and green
after regeneration. Verify both directions once.

**Commit suggestion:** `ci(contracts): fail on a stale tool surface`

### Phase 2 — mq-agent checks against it

### Task 4: Consumer manifest and its honesty test

**Purpose:** declare what mq-agent depends on, so it can be compared.

**Files:**

- Create: `.mq/mcp-tool-requirements.json`,
  `schemas/mcp_tool_requirements.schema.json`
- Create: `tests/test_mcp_tool_requirements.py`
- Modify: `pyproject.toml` force-include (the schema must ship in the wheel)

**Steps:**

1. Test first: every literal tool reference (the same extraction measured above,
   26 names today) is in the manifest, and no manifest entry is unreferenced.
2. Argument capture: drive each bridge helper (`review_file`, `review_diff`,
   `review_repo`, the `brain_record_*` calls) with a recording fake bridge,
   the way `FakeReviewBridge` does. Assert that the sent keys are within
   `arguments ∪ optional_arguments`.
3. Fill `max_safety_class` from what each flow assumes today. Read-only review
   flows get B. Anything run through `mcp run --approve` gets its current
   class.

**Expected result:** the manifest validates. A new `call_tool("x", …)` without
a manifest entry fails the test.

**Commit suggestion:** `feat(compat): declare the MCP tools mq-agent depends on`

### Task 5: MQC019–MQC023 in the compatibility report

**Purpose:** the actual check.

**Files:**

- Modify: `mq_agent/tools/stack_compatibility.py`: a `_tool_contract_findings()`
  called from `_relationships()`, and `release_blockers()`
- Modify: `schemas/mq_stack_compatibility.schema.json` (append the codes)
- Create: `tests/test_stack_tool_contracts.py`

**Steps:**

1. One failing test per code, built from fixture producer and consumer files.
   Add one test proving that a missing artifact is `UNAVAILABLE` and not a
   release blocker.
2. Implement. Findings carry `repos`, a provenance pointer (file plus tool name)
   and the concrete parameter or class.
3. CI mode: map the producer path with `_ci_repo_path`. With only mq-agent checked
   out, the result is `MQC023`/UNAVAILABLE, never FAIL.
4. Check the exit code under the existing `_STATUS_ORDER`.

**Expected result:** fixture tests green. A real run against the local stack
reports the current state, with the image tools flagged as Phase 3 work.

**Commit suggestion:** `feat(compat): check MCP tool names, classes and arguments`

### Task 6: Docs and ROADMAP

**Files:**

- Modify: `ROADMAP.md`: check the Phase 3 item and replace the deferred
  section with the shipped state and remaining phases
- Modify: `docs/STACK_CONTRACT_GATE.md`: replace the fictional
  `mq-mcp.tools.v1` example with `mq-mcp.tool-surface.v1`
- Modify: `CHANGELOG.md`

**Commit suggestion:** `docs(compat): record MCP tool contract checking`

### Phase 3 — second producer and hardening

### Task 7: mq-image-analyze publishes the same artifact

**Purpose:** resolve `image_perception` and `observe_architecture`, which
mq-agent calls and mq-mcp does not register.

**Files:** the same export and CI as Tasks 2–3, in mq-image-analyze. Then add
`producer: mq-image-analyze` entries to the mq-agent manifest.

**Expected result:** neither tool remains unattributed.

### Task 8: Fail closed instead of guessing the class

**Purpose:** stop name-prefix guessing from under-classifying a tool, as
`extract_coding_conventions` shows (declared C, guessed read-only).

**Decision needed:** this changes `mcp run` behavior. When the server gives no
class, the class becomes `unknown` and the call is blocked, where today the
name is classified. Recommendation: do it, but only for tools whose producer
publishes a surface. Name guessing remains for third-party servers.

**Files:** `mq_agent/tools/mcp_registry.py`, `mq_agent/tools/mcp_bridge.py`,
`tests/test_mcp.py`

**Commit suggestion:** `fix(mcp): fail closed when a declared producer gives no class`

### Task 9: Optional live comparison (`--live`)

**Purpose:** detect a running server that differs from the committed surface,
like the stale `8d7d70b` process today.

**Steps:** fetch `/tools` and `/runtime-identity`, compare with the
artifact and report `MQC024` (WARN) with both commits. A server that is down
is `UNAVAILABLE`. Never part of the release gate.

**Commit suggestion:** `feat(compat): compare the live MCP surface with the declared one`

## Open decisions for the operator

1. **Artifact location and name.** The recommendation is
   `contracts/tool_surface.v1.json` in mq-mcp, contract
   `mq-mcp.tool-surface.v1`. The alternative is extending
   `docs/tool_contracts.json` with parameters, which mixes a hand-maintained
   file with generated data.
2. **Task 8 (fail closed).** It is a behavior change in `mcp run`. The
   recommendation is yes, scoped to declared producers.
3. **Version.** No version is assigned today. Phases 1–2 are one coherent
   release, and Phase 3 can follow without one.

## Recommended first task

Task 1, then Task 2, in mq-mcp. Nothing in mq-agent can be checked until the
producer publishes its surface.
