# Roadmap

The detailed roadmap lives in [docs/ROADMAP.md](docs/ROADMAP.md).

## Status

Current phase:

```text
active / stable maintenance
```

The roadmap is complete through `v1.4.0` - mq-image-analyze perception tool
integration. The next roadmap track is `v2.0.0`, focused on ecosystem-scale
orchestration maturity, including the MQ Skill System v2.0 work that should be
owned centrally by mq-agent rather than by individual repos such as coolThing.

## Done

- [x] Stable orchestration platform
- [x] mq-mcp review runtime integration
- [x] Semantic memory, risk review, architecture memory and learn routing
- [x] mq-image-analyze perception tool integration

## Maintenance notes

- Use [docs/MQ_SKILL_SYSTEM.md](docs/MQ_SKILL_SYSTEM.md) as the v2.0.0 contract baseline.
- Plan `v2.0.0` around MQ Skill System ownership, ecosystem contracts and operator UX maturity.
- Keep repo-local `SKILLS.md` files as inputs; define cross-repo MQ Skill System v2.0 behavior in mq-agent.
- Keep root README, command docs and `docs/ROADMAP.md` aligned.
- Leave new roadmap ideas unscheduled until they have a clear release target.
