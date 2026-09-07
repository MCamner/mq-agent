# Task-aware skill selection

`mq-agent skills` profiles a task and selects existing local skills. It does not
execute skills, call an LLM, access the network, or change the repository.

```bash
mq-agent skills inventory --repo mq-agent --json
mq-agent skills profile "fix CI and open PR" --repo mq-agent --json
mq-agent skills route "Implementera runtime provenance i mq-agent och öppna PR" \
  --repo mq-agent --target codex --explain
mq-agent skills route "audit mq-agent" --repo mq-agent --target both --json
```

`--repo` accepts an existing directory or a repository name. A name resolves
to the current checkout when its repo contract matches, otherwise under the
home folder. An explicit context-pack `--repos-root` takes precedence. `--vault` overrides `$MQ_OBSIDIAN_DIR` (default: `~/mqobsidian`). The
vault must provide `.mq/skill-selection-vocabulary.json` and the schemas
`skill-selection-vocabulary.v1`, `mq.skill-profile.v1`, and `mq.skill-route.v1`.
Missing or invalid contracts produce `invalid`, never a private fallback.

## Ownership and discovery

mqobsidian owns the vocabulary and schemas. Each source repository owns its
`skill-profile.json` sidecars. mq-agent owns inventory and selection execution.
Eight existing mq-agent skills have profiles in this first delivery.

Inventory reads `skills/*/skill-profile.json` and existing repo-owned discovery
profiles in `.agents/skills/` and `.claude/skills/`. Central `skills/` sources
win when present. Duplicate profiles must agree. The source `SKILL.md` must
exist and its frontmatter name must equal the profile and directory name.
Unprofiled skills are listed in inventory but are not candidates.

Declared support is separate from observation: Codex discovery requires a
readable matching `.agents/skills/<id>/SKILL.md`; Claude uses `.claude/skills/`.
A stale or different discovered document is unavailable. An inactive profile
is unavailable even when files exist. Profile validation rejects unknown
facets, unresolved supersedes references and cycles.

## Selection rules

Task terms match case-insensitively at word boundaries, including Swedish
aliases supplied by the owner vocabulary. Facets are deterministic and sorted;
no free-form description is used as a routing signal.

1. A task risk matching `required_for` makes the skill required, before ranking.
2. Optional skills need at least one matching intent, domain or risk. When both
   task and skill declare intents, disjoint intents exclude the optional skill.
   This prevents a read-only audit skill from matching implementation merely
   through a shared repo domain.
3. Order by required status, number of matching dimensions, number of matching
   facets, repo scope before stack-only scope, then skill ID alphabetically.
4. A surviving skill supersedes a non-required skill only at equal or greater
   relevance. Replaced skills cannot themselves suppress other candidates.
5. Keep at most the vocabulary's optional budget, within its total budget.
   Required skills are never dropped; required overflow gets a budget reason.

For `both`, optional skills may serve one target. Required skills must be
available for every requested target; missing targets appear in
`missing_required`. Unsupported and undiscoverable are separate findings.

## Output and failures

`--json` emits only `mq.skill-route.v1`; `--explain` adds per-candidate decisions
to human output. With both flags, JSON takes precedence. Inventory and profile
JSON are inspection output, not additional versioned route contracts.

| State | Meaning | CLI exit |
| --- | --- | --- |
| complete | Skills selected; every required skill resolved | 0 |
| empty | No eligible selection and no missing requirement | 0 |
| partial | At least one required target unavailable | 1 |
| invalid | Vocabulary, schema or profile malformed/unavailable | 2 |

Codes SKS001–SKS009 are defined in mqobsidian's route schema. Human explanations
are independent of these stable codes. Routes contain no timestamp, absolute
source paths or random ID, so identical inputs produce identical ordered JSON.

`context pack` renders a Selected skills section and reports unavailable or
invalid selection there. It does not add fields to `context-pack.v1` or change
its existing command exit behavior. Use `skills route --json` when a machine
consumer needs the standalone route and its exit status.

## Validation

Run `python -m pytest tests/test_skill_selection.py tests/test_context_pack_cmd.py`.
Contract snapshots and golden data in `tests/fixtures/skill_selection/` are
test-only fixtures sourced from mqobsidian main (PR #98); runtime reads only
the selected vault. The golden test locks ordered JSON and explain decisions.

Contract changes must land in mqobsidian before deploying this consumer.
Later ecosystem audit integration and effectiveness tracking are separate work.
