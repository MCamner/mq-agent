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
The active planning track also connects mq-agent's perception routing with
`mq-mcp` Release Gate v2 and a terminal-first operator status flow.

## Done

- [x] Stable orchestration platform
- [x] mq-mcp review runtime integration
- [x] Semantic memory, risk review, architecture memory and learn routing
- [x] mq-image-analyze perception tool integration
- [x] Initial MQ Release Operator command flow
- [x] Initial mq-mcp Release Gate v2 bridge and operator status rendering

## Maintenance notes

- Use [docs/MQ_SKILL_SYSTEM.md](docs/MQ_SKILL_SYSTEM.md) as the v2.0.0 contract baseline.
- Use the 8-week ecosystem track in [docs/ROADMAP.md](docs/ROADMAP.md) to plan
  perception contracts, Release Gate v2, review routing, operator status and
  cross-repo hardening.
- Plan `v2.0.0` around MQ Skill System ownership, ecosystem contracts and operator UX maturity.
- Keep repo-local `SKILLS.md` files as inputs; define cross-repo MQ Skill System v2.0 behavior in mq-agent.
- Keep root README, command docs and `docs/ROADMAP.md` aligned.
- Start with contracts, routing, release gate and terminal operator UI before
  browser UI or richer reports.

## Remaining operator work

- [x] repo-signal readiness export integration
- [x] Release Gate v2 perception artifact checks
- [x] Full stack-health dashboard across mq-agent, mq-mcp, repo-signal,
  mq-image-analyze and mq-hal
- [x] mqlaunch entrypoint for review/release workflow
