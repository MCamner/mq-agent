# mqlaunch Tool Audit

This audit records the mqlaunch tools used by the mq-agent release workflow and
the current gaps seen from headless/operator usage.

## Verified Commands

| Command | Status | Notes |
| ------- | ------ | ----- |
| `mqlaunch agent mcp-status` | Works | `mq-mcp` is reachable on `:8765` with 100 tools and valid contracts. |
| `mqlaunch agent mcp-tools` | Works | Lists the `mq-mcp` tool catalog and safety classes. |
| `mqlaunch agent release-workflow --repo . --target v1.4.0` | Works | Renders the operator workflow: dashboard, review repo, release gate, review release. |
| `mqlaunch agent release-check` | Works with caveat | Returns "Ready to release", but the listed steps are suggest-mode plan steps, not deterministic release execution. |
| `mqlaunch agent review release --repo . --target v1.4.0` | Routes correctly, gate blocked | Calls `mq-agent review release`, then `mq-mcp release_gate_run`; blocked because `mq-agent` lacks Release Gate v2 release/tool contract schema inputs. |

## Current Gaps

| Area | Gap | Next fix |
| ---- | --- | -------- |
| `mq-agent` Release Gate input | `mqlaunch agent review release` reports `contracts_valid` blocked because no release/tool contract schema is present, and warns that `docs/tool_contracts.json` is absent. | Add the release/tool contract schema inputs expected by Release Gate v2 or teach the gate which mq-agent contract docs satisfy this check. |
| `mq-image-analyze` availability | `mqlaunch agent mcp-status` reports `mq-image-analyze` is not reachable on `:8766`. | Start `mq-image-analyze` when perception tools need live OCR or visual analysis. |
| `mqlaunch agent release-check` semantics | The command is useful as a plan/readiness prompt, but its steps are skipped in suggest mode. | Keep using `./release-check.sh` for deterministic repo verification until mqlaunch exposes a deterministic release-check route. |
| `run_mqlaunch_version` | Output is TUI-heavy and not cleanly parseable in headless mode. | Add `mqlaunch version --plain` or `--json`. |
| `run_mqlaunch_system_check` | No `--no-tui` or `--json` mode. | Add `mqlaunch system check --json`. |
| `run_mqlaunch_perf` | Opens an interactive TUI and has no parseable report mode. | Add `mqlaunch perf --report`. |
| `run_mqlaunch_demo` | Interactive only. | Add `mqlaunch demo --script`. |
| `run_mqlaunch_bundle` | TUI-gated bundle flow does not report an output path headlessly. | Add `mqlaunch bundle --out <path>`. |
| `run_mqlaunch_ask` | Requires `OPENAI_API_KEY`; without it the fallback is not useful for MCP/headless usage. | Add `mqlaunch ask --no-clipboard` or an explicit error path. |

## Practical Verification Order

Use mqlaunch for operator-facing routing checks:

```bash
mqlaunch agent mcp-status
mqlaunch agent mcp-tools
mqlaunch agent release-workflow --repo . --target v1.4.0
mqlaunch agent review release --repo . --target v1.4.0
```

Use repo-local deterministic checks for release confidence:

```bash
./release-check.sh
```

