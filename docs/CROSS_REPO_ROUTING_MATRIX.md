# Cross-Repo Routing Matrix

MQ Skill System v2.0 routes work to the repo that already owns the behavior.
mq-agent may orchestrate, summarize and render operator output, but it must not
duplicate neighboring repos' domain logic.

| User intent | Primary owner | Skill or command | Output contract | Escalation rule |
| ----------- | ------------- | ---------------- | --------------- | --------------- |
| Audit repository health | mq-agent | `mq-agent audit .` | `summary`, `steps`, `verification` | Escalate static scoring details to repo-signal. |
| Check release readiness | mq-mcp | `mq-agent release status` / `mq-agent review release` | `status`, `score`, `checks`, `blockers`, `warnings`, `next_actions` | mq-agent renders; mq-mcp owns gate rules. |
| Review file, diff or repo | mq-mcp | `mq-agent review file/diff/repo` | `findings`, `severity_summary`, `next_actions`, `raw_mcp_result` | mq-agent forwards flags and visual context only. |
| Analyze screenshot, UI image or diagram | mq-image-analyze | `mq-agent review perception <image>` | `visual_summary`, `ocr_text`, `detected_regions`, `risk_signals`, `confidence` | mq-agent normalizes perception JSON; image logic stays in mq-image-analyze. |
| Score README and publish readiness | repo-signal | `mq-agent signal .` / `mq-agent score .` | `scores`, `readme`, `publish_checklist`, `focus_areas`, `next_actions` | mq-agent surfaces repo-signal output; repo-signal owns scoring. |
| Show stack health | mq-agent | `mq-agent dashboard` | `status`, `components`, `next_action` | Component-specific failures route to the owning repo. |
| Launch review/release workflow | macos-scripts | `mqlaunch agent release-workflow` | `steps`, `mqlaunch`, `repo`, `target` | mqlaunch is only the human entrypoint; mq-agent owns workflow details. |
| Local operator status and command routing | mq-hal | `mq-hal` / future mq-agent bridge | `summary`, `health`, `recommended_action` | mq-hal owns local runtime/operator summaries. |

## Overlap Rules

* Prefer the narrowest owner that already owns the domain logic.
* Use mq-agent for orchestration, routing, approval UX and operator rendering.
* Use mq-mcp for deterministic release checks, review cognition, safety classes
  and contract drift detection.
* Use repo-signal for repo scoring, publish readiness and static repository
  intelligence.
* Use mq-image-analyze for OCR, screenshot, diagram and visual summaries.
* Use mqlaunch for the terminal entrypoint only.
* Use mq-hal for local runtime status and operator command routing.

## Escalation Rules

* Unknown or ambiguous ownership should return a dry-run routing preview before
  execution.
* Cross-repo routing must preserve approval gates; mq-agent must not auto-run
  write-capable or subprocess actions.
* If an owning repo is unavailable, mq-agent should report the missing component
  and the next command to restore it.
* No route may silently replace another repo's contract with local heuristics.
