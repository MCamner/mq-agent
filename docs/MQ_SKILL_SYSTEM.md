# MQ Skill System v2.0

mq-agent owns the central routing and validation behavior for MQ Skill System
v2.0. Repo-local skill files remain local indexes. mq-agent should read,
summarize and validate them, but it must not implement repo-local skills inside
the orchestration runtime.

## Goal

MQ Skill System v2.0 gives the mq ecosystem one predictable way to discover,
route and report skill capabilities across repositories.

Cross-repo ownership and escalation rules live in
[`CROSS_REPO_ROUTING_MATRIX.md`](CROSS_REPO_ROUTING_MATRIX.md).
Skill quality scoring lives in
[`SKILL_QUALITY_REVIEW.md`](SKILL_QUALITY_REVIEW.md).

The system must stay:

* terminal-native
* repo-aware
* dry-run friendly
* approval gated
* explicit about tool ownership
* useful without autonomous execution

## Ownership

| Area | Owner | Notes |
| ---- | ----- | ----- |
| Repo-local skill index | Each repository | Usually `SKILLS.md`; describes local capabilities |
| Cross-repo discovery | mq-agent | Finds and summarizes configured repo skill indexes |
| Routing and validation | mq-agent | Chooses where a request belongs and validates contract shape |
| Cognition and review | mq-mcp | Review, risk, architecture reasoning and semantic retrieval |
| Visual perception | mq-image-analyze | Diagram, screenshot, OCR and topology observations |
| Repo intelligence | repo-signal | Static repo summary, scoring and signal packs |
| Launch surface | mqlaunch | Human entrypoint and menu/prompt bridge |

## Contract Versions

MQ Skill System v2.0 should use explicit versioned contracts:

| Contract | Version | Purpose |
| -------- | ------- | ------- |
| Skill index | `mq.skill_index.v1` | Repo-local list of available skills |
| Skill record | `mq.skill.v1` | One skill entry normalized by mq-agent |
| Routing decision | `mq.skill_route.v1` | Selected owner, confidence and required approvals |
| Ecosystem summary | `mq.ecosystem_skills.v1` | Cross-repo inventory and health summary |
| Skill execution | `mq.skill_execution.v1` | Approval-gated execution plan/result |

Contract version strings should appear in JSON output and docs examples when
the runtime behavior is implemented.

## Skill Index Contract

A repo-local skill index should describe local skill capabilities without
granting execution authority.

Required fields:

* `schema_version`
* `repo`
* `skills`

Recommended shape:

```json
{
  "schema_version": "mq.skill_index.v1",
  "repo": "mq-agent",
  "skills": [
    {
      "id": "release-readiness",
      "name": "Release readiness",
      "summary": "Check release docs, tests and publish readiness.",
      "owner": "mq-agent",
      "triggers": ["release", "tag", "publish"],
      "safety_class": "B",
      "requires_approval": false,
      "inputs": ["repo_path"],
      "outputs": ["summary", "checks", "next_actions"]
    }
  ]
}
```

Markdown `SKILLS.md` files may remain human-readable, but mq-agent should
normalize discovered entries into this shape before routing.

## Skill Record Rules

Each normalized skill record should include:

* stable `id`
* human-readable `name`
* short `summary`
* owning tool or repo
* trigger phrases
* safety class
* approval requirement
* expected inputs
* expected outputs
* failure behavior when known

Skill records must not include secrets, local credentials or hidden command
execution. A skill entry describes capability; it does not authorize execution.

## Output Contracts

Operational skills should declare predictable output fields in repo-local
`SKILLS.md` metadata:

```text
Outputs: summary, checks, next_actions
```

mq-agent normalizes `Output:` and `Outputs:` lines into the `outputs` list on
each `mq.skill.v1` record. These names describe the stable human-readable and
JSON-friendly sections operators can expect from the command. Missing output
metadata is allowed during migration and normalizes to an empty list.

Recommended field names:

* `summary` — compact human-facing result
* `checks` — deterministic check list
* `findings` — review findings or warnings
* `steps` — planned or executed steps
* `next_actions` — recommended operator actions
* `raw_mcp_result` — pass-through result from an owning MCP/tool runtime

## Routing Decision Contract

When mq-agent routes a user request to a skill owner, the decision should be
inspectable.

Recommended shape:

```json
{
  "schema_version": "mq.skill_route.v1",
  "request": "review this repo for release readiness",
  "selected_skill": "release-readiness",
  "owner": "mq-agent",
  "confidence": "high",
  "safety_class": "B",
  "requires_approval": false,
  "reason": "Request matches release readiness triggers and needs local repo checks.",
  "next_action": "Run dry-run release readiness checks."
}
```

Routing should prefer the narrowest owner that already owns the behavior. For
example, mq-agent may route review cognition to mq-mcp, but it must not
reimplement review scoring locally.

## Implementation Order

1. [x] Document the contracts and ownership boundaries.
2. [x] Add read-only discovery of repo-local `SKILLS.md` files.
3. [x] Normalize discovered skills into `mq.skill.v1` records.
4. [x] Add a dry-run skill routing preview with JSON output.
5. [x] Add ecosystem skill summaries across configured repos.
6. [x] Add approval-gated execution only for existing command surfaces.
7. [x] Update examples, command docs and migration notes after command behavior exists.

## v2.0 Readiness Gates

Before MQ Skill System v2.0 is considered stable:

* Every active MQ repo should expose `SKILLS.md`.
* Every listed skill path should point to a real `skills/<name>/SKILL.md`.
* Stable skills should have trigger-strong descriptions and near-miss cases.
* Priority skills should have eval prompts for should-trigger and
  should-not-trigger behavior.
* Operational skills should define predictable output contracts.
* Cross-repo routing should have a documented ownership matrix.
* Release validation should catch broken skill docs and stale skill references.
* Stable skills should have a quality review score and concrete fixes for gaps.

## Commands

Read-only discovery and normalization:

```bash
mq-agent skill list .
mq-agent skill list . --json
mq-agent skill route "check release readiness"
mq-agent skill route "audit this repo" --json
mq-agent skill ecosystem
mq-agent skill ecosystem ../mq-agent ../mq-mcp --json
mq-agent skill run "list skills"
mq-agent skill run "list skills" --approve
```

`--json` returns the `mq.skill_index.v1` discovery contract with normalized
`mq.skill.v1` records for `skill list`, and the `mq.skill_route.v1` routing
decision for `skill route`. `skill ecosystem --json` returns
`mq.ecosystem_skills.v1`. `skill run --json` returns `mq.skill_execution.v1`.
Only `skill run --approve` executes, and only for supported existing `mq-agent`
command surfaces.

## Migration Notes

Existing v1.x command behavior remains valid. MQ Skill System v2.0 adds a skill
metadata layer around existing commands; it does not replace the commands
operators already use.

What changes:

* `SKILLS.md` is now treated as a repo-local skill index.
* `mq-agent skill list` discovers and normalizes `SKILLS.md` into
  `mq.skill_index.v1` and `mq.skill.v1`.
* `mq-agent skill route` previews routing decisions using `mq.skill_route.v1`.
* `mq-agent skill ecosystem` summarizes MQ skill inventory across repos using
  `mq.ecosystem_skills.v1`.
* `mq-agent skill run` requires `--approve` and only executes supported
  existing `mq-agent` command surfaces.

What does not change:

* `mq-agent audit`, `release-check`, `signal`, `review`, `memory`, `task`,
  `swarm`, `mcp` and `browser` commands remain direct entrypoints.
* mq-agent still does not implement repo-local skill behavior directly.
* mq-mcp still owns review cognition, risk, architecture reasoning and semantic
  retrieval.
* mq-image-analyze still owns visual perception behavior.
* No skill routing command performs hidden execution or memory mutation.

Recommended migration path:

1. Keep existing direct commands working.
2. Add or clean up repo-local `SKILLS.md` indexes.
3. Use `mq-agent skill list --json` to validate normalized records.
4. Use `mq-agent skill route "<request>" --json` before adding execution paths.
5. Use `mq-agent skill ecosystem --json` to find missing or stale skill indexes.
6. Add `--approve` only when intentionally running a supported existing
   `mq-agent` command through `skill run`.

## Non-Goals

* No autonomous skill execution.
* No hidden mutation of repositories or memory stores.
* No local duplicate of mq-mcp cognition.
* No direct implementation of repo-local skills inside mq-agent.
* No breaking changes to existing commands without migration notes.

## Validation

Every implementation step should include:

* contract-shape tests
* dry-run output tests
* approval-gate tests for write-capable behavior
* docs examples for new command behavior
* graceful handling when a repo has no `SKILLS.md`
