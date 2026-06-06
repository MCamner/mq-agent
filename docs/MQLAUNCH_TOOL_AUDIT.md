# mqlaunch Tool Audit

This audit records the mqlaunch tools used by the mq-agent release workflow and
the current gaps seen from headless/operator usage.

## Verified Commands

| Command | Status | Notes |
| ------- | ------ | ----- |
| `mqlaunch agent mcp-status` | Works | `mq-mcp` is reachable on `:8765` with 100 tools and valid contracts. |
| `mqlaunch agent mcp-tools` | Works | Lists the `mq-mcp` tool catalog and safety classes. |
| `mqlaunch agent release-workflow --repo . --target v1.4.0` | Works | Renders the operator workflow: dashboard, review repo, release gate, review release. |
| `mqlaunch agent release-check` | Works with caveat | Returns "Ready to release", but the listed steps are suggest-mode plan steps. |
| `mqlaunch agent release-check --execute` | Works | Runs deterministic repo release checks through `./release-check.sh` when present. |
| `mqlaunch agent review release --repo . --target v1.4.0` | Routes correctly | Calls `mq-agent review release`, then `mq-mcp release_gate_run`; use `--test-cmd` when the gate should execute tests instead of warning. |

## Current Gaps

| Area | Gap | Next fix |
| ---- | --- | -------- |
| Release Gate test execution | Without `--test-cmd`, `tests_pass` remains a warning because the gate stays read-only by default. | Pass `--test-cmd "uv run pytest -q"` through `mq-agent release gate/status` or `mqlaunch agent review release`. |
| Non-MCP repo contract handling | Tool safety classes should not block repos that do not expose an MCP server. | `mq-mcp` skips `safety_classes_valid` for non-MCP repos and only warns when no release schema is present. |
| `mq-agent` Release Gate input | `mq-agent` needs a release/tool contract schema anchor because it participates in the release workflow even though it is not an MCP tool server. | `contracts/release_gate_v2.schema.json` is present and should be committed with mq-agent release docs. |
| `mq-image-analyze` availability | `mqlaunch agent mcp-status` can report `mq-image-analyze` is not reachable on `:8766`. | `mqlaunch doctor` now warns when `mq-image-analyze` is down so perception users see the missing dependency before live OCR/visual analysis. |
| `mqlaunch agent release-check` semantics | The default command is useful as a plan/readiness prompt, but its steps are skipped in suggest mode. | Use `mqlaunch agent release-check --execute` for deterministic repo verification. |
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
mqlaunch agent review release --repo . --target v1.4.0 --test-cmd "uv run pytest -q"
```

Use repo-local deterministic checks for release confidence:

```bash
./release-check.sh
```
