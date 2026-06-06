# Perception Integration

`mq-agent` treats perception as routed context, not local image analysis.

`mq-image-analyze` owns OCR, screenshot analysis, diagram interpretation,
visual summaries, detected regions and perception confidence. `mq-agent` owns
the command surface, dry-run behavior, MCP routing and normalization into the
review context used by downstream workflows.

## Command Surface

```bash
mq-agent review perception docs/screenshot.png
mq-agent review perception docs/screenshot.png --json
mq-agent review perception docs/screenshot.png --dry-run
mq-agent review repo . --architecture-image docs/architecture.png
mq-agent review repo . --visual docs/architecture.png
```

`run-tool` can also delegate directly to the perception MCP tools:

```bash
mq-agent run-tool observe_architecture --arg image_path=docs/arch.png --json
mq-agent run-tool image_ocr --arg image_path=docs/screenshot.png --json
```

## Normalized Payload

`mq_agent/perception/adapter.py` normalizes `mq-image-analyze` output into this
shape:

```json
{
  "source_type": "screenshot",
  "source_path": "docs/screenshot.png",
  "ocr_text": "",
  "visual_summary": "",
  "detected_regions": [],
  "risk_signals": [],
  "confidence": "medium",
  "contract": {
    "ok": true,
    "errors": []
  }
}
```

Allowed `source_type` values:

```text
screenshot
diagram
ui
terminal
browser
```

Allowed `confidence` values:

```text
low
medium
high
```

## Fallback Behavior

If `mq-image-analyze` is not reachable, `mq-agent` returns a fallback perception
payload with empty visual fields, `confidence: medium`, and a warning. This
keeps the operator workflow inspectable without pretending that image analysis
was performed.

## Safety Boundary

```text
mq-agent routes and validates shape.
mq-image-analyze extracts visual information.
mq-mcp evaluates review and release contracts.
```

`mq-agent` must not implement OCR, diagram interpretation or screenshot
analysis locally.

## Verification

Perception routing is covered by:

```bash
uv run pytest tests/test_mcp.py tests/test_release_operator.py -q
```

