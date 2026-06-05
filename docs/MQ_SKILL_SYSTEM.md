# MQ Skill System v2.0

mq-agent owns the central routing and validation behavior for MQ Skill System
v2.0. Repo-local skill files remain local indexes. mq-agent should read,
summarize and validate them, but it must not implement repo-local skills inside
the orchestration runtime.

## Goal

MQ Skill System v2.0 gives the mq ecosystem one predictable way to discover,
route and report skill capabilities across repositories.

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
3. [ ] Normalize discovered skills into `mq.skill.v1` records.
4. [ ] Add a dry-run skill routing preview with JSON output.
5. [ ] Add ecosystem skill summaries across configured repos.
6. [ ] Add approval-gated execution only for existing command surfaces.
7. [ ] Update examples and command docs after command behavior exists.

## Commands

Read-only discovery:

```bash
mq-agent skill list .
mq-agent skill list . --json
```

`--json` returns the `mq.skill_index.v1` discovery contract. It does not parse
or execute repo-local skill behavior.

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
