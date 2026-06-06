"""Minimal perception contract validation."""
from __future__ import annotations

from typing import Any

VALID_SOURCE_TYPES = {"screenshot", "diagram", "ui", "terminal", "browser"}
VALID_CONFIDENCE = {"low", "medium", "high"}


def validate_perception_payload(payload: dict[str, Any]) -> dict[str, Any]:
    required = ["source_type", "source_path", "ocr_text", "visual_summary", "risk_signals", "confidence"]
    missing = [key for key in required if key not in payload]
    if missing:
        return {"ok": False, "errors": [f"Missing field: {key}" for key in missing]}
    errors = []
    if payload["source_type"] not in VALID_SOURCE_TYPES:
        errors.append(f"Invalid source_type: {payload['source_type']}")
    if payload["confidence"] not in VALID_CONFIDENCE:
        errors.append(f"Invalid confidence: {payload['confidence']}")
    if not isinstance(payload["risk_signals"], list):
        errors.append("risk_signals must be a list")
    return {"ok": not errors, "errors": errors}
