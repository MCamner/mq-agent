# v1.4.0 Scope

`mq-agent` v1.4.0 is the perception-routing release.

The release adds operator-facing routes for visual context while keeping image
analysis outside `mq-agent`.

## Included

* Register `mq-image-analyze` as the visual perception MCP endpoint.
* Route `observe_architecture` and `image_ocr` through `mq-agent run-tool`.
* Add `mq-agent review perception <image>` for normalized perception context.
* Pass architecture image context into review commands through
  `--architecture-image` / `--visual`.
* Show `mq-image-analyze` availability in stack-health and dashboard output.
* Keep Release Gate v2 rendering delegated through `mq-mcp`.

## Not Included

* No OCR, screenshot analysis, diagram analysis or visual model logic is
  implemented inside `mq-agent`.
* No local duplication of `mq-mcp` Release Gate v2 checks.
* No browser UI requirement; terminal status and JSON output are the first
  operator surfaces.
* No automatic fix branches or PR comments.

## Ownership Boundary

| Layer | Owner |
| ----- | ----- |
| Operator commands, dry-run UX and routing | `mq-agent` |
| OCR, screenshot analysis, diagram analysis and visual summaries | `mq-image-analyze` |
| Release Gate v2 rules and deterministic release decisions | `mq-mcp` |
| Repo readiness exports and repository intelligence | `repo-signal` |
| Runtime health and safe operator command routing | `mq-hal` |

## Verification

The v1.4.0 scope is verified through:

```bash
uv run pytest tests/test_mcp.py tests/test_release_operator.py -q
./release-check.sh
```

