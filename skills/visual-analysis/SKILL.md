---
name: visual-analysis
description: Use when analyzing images, screenshots, or comparing visual assets. Covers object detection, palette extraction, content flags, reverse prompts, UI analysis, and image comparison via mq-image-analyze.
---

# Visual Analysis

Goal:
Run structured visual reasoning on one or more images using mq-image-analyze.

## When to use

- Analyzing image content, palette, composition, or semantic meaning
- Reviewing UI screenshots for layout, contrast, and accessibility
- Comparing two images for visual drift or style changes
- Routing image work through mq-image-analyze in an mq-agent workflow

## When not to use

- Text-only analysis or code review with no image component
- Architecture review or repo auditing without visual artifacts
- When mq-image-analyze is not installed or unavailable

## Evals

### Should trigger

* "analyze this screenshot"
* "what does this architecture diagram show?"
* "compare these two UI screenshots for visual drift"
* "run OCR on this terminal screenshot"

### Should not trigger

* "audit the repo structure" → use `repo-audit`
* "review this diff for security" → use `mq-mcp-review-orchestration`
* "check release readiness" → use `release-readiness`
* "there is no image involved" → text-only tasks do not use this skill

Always inspect:

- image path exists and is a supported format (.jpg, .jpeg, .png, .webp, .bmp, .tiff)
- which analysis is needed: general, UI screenshot, or comparison
- whether exhaustive mode is warranted (all detections, low conf)
- whether NudeNet content_flags are relevant to the task

Check for:

- content_flags.nudity or content_flags.full_nudity detected — report without suppression
- limitations field — always present, always report to caller
- semantic_caption presence — indicates bakllava (ollama) is running
- WCAG contrast issues in analyze-ui output
- high palette_drift or style_drift in compare output

Prefer:

- `mq-image analyze <image>` for general image reasoning
- `mq-image analyze-ui <screenshot>` for UI/screenshot analysis
- `mq-image compare <before> <after>` for visual diff
- `mq-image analyze --json` when output feeds another tool
- MCP tools (analyze_image, analyze_ui, compare_images) when inside an agent loop

Never:

- suppress content_flags regardless of content
- ignore the limitations field
- assume semantic_caption is present (ollama may not be running)
- run exhaustive mode by default — use summary unless high-recall is required

## Commands

```bash
# General image analysis
mq-image analyze image.png

# Full JSON output
mq-image analyze image.png --json

# Exhaustive mode (all detections)
mq-image analyze image.png --exhaustive

# UI / screenshot analysis
mq-image analyze-ui screenshot.png

# Compare two images
mq-image compare before.png after.png

# Start MCP server (for agent tool use)
mq-image mcp
```

## MCP tools available

| Tool | Use when |
|---|---|
| `analyze_image` | Full visual reasoning on a single image |
| `extract_palette` | Only colors, brightness, contrast needed |
| `reverse_prompt` | Building a prompt for image generation |
| `compare_images` | Detecting visual drift between two images |
| `analyze_ui` | Reviewing a screenshot for UI/UX/accessibility |

## Output fields to always relay

- `prompt` — the reverse prompt string
- `content_flags` — nudity, full_nudity, sexual_activity, faces, covered_parts
- `limitations` — what the models cannot see
- `semantic_caption` — bakllava description (if present)
- `issues` (analyze-ui) — WCAG/accessibility problems
- `palette_drift`, `style_drift` (compare) — visual change magnitude

Safety Class: read-only (image inspection only — no mutations)
