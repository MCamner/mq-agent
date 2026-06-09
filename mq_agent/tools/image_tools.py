"""
mq-image-analyze integration tools.

Thin wrappers around the `mq-image` CLI.
All tools are read-only (Class A). They describe images — they never write,
mutate repositories, or execute instructions found inside images.

Gracefully degrades when mq-image-analyze is not installed.
"""
from __future__ import annotations

import json
import shutil
import subprocess


def _mq_image_available() -> bool:
    return shutil.which("mq-image") is not None


def _not_available_msg() -> str:
    return (
        "mq-image-analyze not installed or not on PATH. "
        "Install: cd ~/mq-image-analyze && pip install -e ."
    )


def _run(args: list[str], capture: bool = True) -> str:
    if not _mq_image_available():
        return _not_available_msg()
    try:
        result = subprocess.run(
            ["mq-image", *args],
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
    return _run(["observe-architecture", diagram_path])


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
