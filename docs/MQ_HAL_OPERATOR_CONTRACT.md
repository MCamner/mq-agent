# mq-agent to mq-hal Operator Contract

`mq-agent` is the control-plane truth producer. `mq-hal` is the operator
presentation layer.

This contract defines the read-only JSON surfaces `mq-hal` may consume. `mq-hal`
must not own gates, release decisions, brain writes or repo mutations; it should
show the truth from `mq-agent` and route the operator to the right command.

## Read Surfaces

| mq-hal view | mq-agent source |
| --- | --- |
| `mq-hal stack` | `mq-agent stack cockpit --json` |
| `mq-hal brain-status` | `mq-agent stack brain-gate --json` and cockpit `brain_export` |
| `mq-hal release-status` | `mq-agent stack release-check --json` |
| `mq-hal next-action` | `next_action_contract` from cockpit or dashboard |

`mq-agent dashboard --json` is the compact operator snapshot. It includes the
same `next_action_contract` shape for the top-level action and passes per-repo
contracts through from cockpit rows.

## Next Action Contract

Every operator-facing next action keeps the legacy `next_action` text and adds
`next_action_contract`:

```json
{
  "text": "mq-mcp: commit or stash uncommitted changes",
  "source_command": "mq-agent stack cockpit",
  "severity": "attention",
  "suggested_route": "git hygiene",
  "requires_approval": true,
  "repo": "mq-mcp"
}
```

Required fields:

| Field | Contract |
| --- | --- |
| `text` | Human-readable label. Matches or refines `next_action`. |
| `source_command` | Source command that produced the recommendation. |
| `severity` | One of `info`, `attention`, `blocked`. |
| `suggested_route` | Route, command family or operator surface to show. |
| `requires_approval` | `true` when the route may mutate state. |

Optional fields:

| Field | Contract |
| --- | --- |
| `repo` | Repo slug when the action is repo-specific. |

## Ownership Rules

`mq-hal` may:

* render these JSON payloads
* sort or group actions by severity
* open the suggested route
* ask the operator to run a command

`mq-hal` must not:

* decide release readiness
* write to mqobsidian
* mutate git state
* bypass `--approve` or equivalent operator approval
* reinterpret gates beyond display and routing

When a route requires approval, `mq-hal` should surface that explicitly before
launching a mutating command.
