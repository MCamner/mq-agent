"""
mq-image-analyze integration tools.

Thin wrappers around the `mq-image` CLI.
All tools are read-only (Class A). They describe images — they never write,
mutate repositories, or execute instructions found inside images.

Gracefully degrades when mq-image-analyze is not installed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

#: Perception and architecture observation run the vision pipeline, which can
#: take far longer than the quick commands below.
PIPELINE_TIMEOUT_S = 300


def mq_image_bin() -> str | None:
    """The `mq-image` executable: MQ_IMAGE_BIN, else PATH, else the checkout venv.

    mq-mcp resolves the same checkout venv, so both consumers find the install
    that `uv sync` in ~/mq-image-analyze produces even when it is not on PATH.
    """
    override = os.environ.get("MQ_IMAGE_BIN", "").strip()
    if override:
        return override
    found = shutil.which("mq-image")
    if found:
        return found
    candidate = Path.home() / "mq-image-analyze" / ".venv" / "bin" / "mq-image"
    return str(candidate) if candidate.is_file() and os.access(candidate, os.X_OK) else None


def _mq_image_available() -> bool:
    return mq_image_bin() is not None


def _not_available_msg() -> str:
    return (
        "mq-image-analyze is not installed: no mq-image on PATH, in MQ_IMAGE_BIN "
        "or in ~/mq-image-analyze/.venv. Install: cd ~/mq-image-analyze && uv sync"
    )


def _run(args: list[str], capture: bool = True) -> str:
    binary = mq_image_bin()
    if binary is None:
        return _not_available_msg()
    try:
        result = subprocess.run(
            [binary, *args],
            capture_output=capture,
            text=True,
            timeout=60,
        )
        output = result.stdout.strip()
        if result.returncode != 0 and not output:
            return result.stderr.strip() or f"mq-image exited {result.returncode}"
        return output
    except subprocess.TimeoutExpired:
        return "mq-image timed out (60s)"
    except Exception as exc:  # noqa: BLE001
        return f"mq-image error: {exc}"


def image_version() -> str:
    """Return installed mq-image-analyze version."""
    return _run(["--version"])


def image_doctor() -> str:
    """System readiness check — returns JSON status of all mq-image-analyze dependencies."""
    return _run(["doctor", "--json"])


def image_analyze(image_path: str, mode: str = "local-fast") -> str:
    """Full visual analysis of an image — returns mq-image.analysis.v1 JSON.

    mode: local-fast | local-deep | cloud-verify
    """
    return _run(["analyze", image_path, "--json", "--mode", mode])


def image_observe_architecture(diagram_path: str) -> str:
    """Parse an architecture diagram — returns visual_architecture_observation.v1 JSON."""
    return _run(["observe-architecture", diagram_path, "--json"])


def _run_json(args: list[str]) -> dict[str, Any]:
    """Run one pipeline command and return its JSON object, or {"ok": False, "error"}."""
    binary = mq_image_bin()
    if binary is None:
        return {"ok": False, "error": _not_available_msg()}
    label = f"mq-image {args[0]}"
    try:
        result = subprocess.run(
            [binary, *args], capture_output=True, text=True, timeout=PIPELINE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"{label} timed out after {PIPELINE_TIMEOUT_S}s"}
    except OSError as exc:
        return {"ok": False, "error": f"{label} could not start: {exc}"}
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        return {"ok": False, "error": f"{label} failed: {detail}"}
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        return {"ok": False, "error": f"{label} did not print JSON"}
    if not isinstance(payload, dict):
        return {"ok": False, "error": f"{label} did not print a JSON object"}
    return payload


def observe_architecture_json(image_path: str) -> dict[str, Any]:
    """visual_architecture_observation.v1 for a diagram, via the mq-image CLI."""
    return _run_json(["observe-architecture", image_path, "--json"])


def image_perception_record(
    image_path: str, *, producer: str, source_type: str | None = None,
) -> dict[str, Any]:
    """perception.v1 from one producer (ui, architecture, ocr), via the mq-image CLI."""
    args = ["perceive", image_path, "--producer", producer]
    if source_type:
        args += ["--source-type", source_type]
    return _run_json(args)


def image_analyze_ui(screenshot_path: str) -> str:
    """Analyze a UI screenshot — returns layout regions, WCAG contrast, hierarchy JSON."""
    return _run(["analyze-ui", screenshot_path, "--json"])


def image_compare(before_path: str, after_path: str) -> str:
    """Compare two images for visual drift — returns JSON diff."""
    return _run(["compare", before_path, after_path, "--json"])


def image_status() -> str:
    """Return structured status dict: version + doctor result + tool list."""
    if not _mq_image_available():
        return json.dumps({"available": False, "error": _not_available_msg()})

    version_raw = _run(["--version"])
    doctor_raw = _run(["doctor", "--json"])

    version = version_raw.split()[-1] if version_raw and not version_raw.startswith("mq-image-analyze not") else "unknown"

    doctor: dict = {}
    try:
        doctor = json.loads(doctor_raw)
    except (json.JSONDecodeError, TypeError):
        doctor = {"raw": doctor_raw}

    return json.dumps({
        "available": True,
        "version": version,
        "doctor": doctor,
        "tools": [
            "analyze_image",
            "extract_palette",
            "reverse_prompt",
            "compare_images",
            "analyze_ui",
            "observe_architecture",
            "image_ocr",
        ],
        "safety_class": "A",
        "read_only": True,
    }, indent=2)
