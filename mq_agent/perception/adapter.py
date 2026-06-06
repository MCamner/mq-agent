"""Adapter from mq-image-analyze output into mq-agent perception context."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .contract import validate_perception_payload


def normalize_perception_output(image_path: str, raw: Any, source_type: str = "screenshot") -> dict[str, Any]:
    data = _unwrap(raw)
    payload = {
        "source_type": source_type,
        "source_path": image_path,
        "ocr_text": str(data.get("full_text") or data.get("ocr_text") or ""),
        "visual_summary": str(data.get("summary") or data.get("visual_summary") or data.get("description") or ""),
        "detected_regions": data.get("regions") or data.get("detected_regions") or [],
        "risk_signals": data.get("risk_signals") or [],
        "confidence": str(data.get("confidence") or "medium"),
    }
    validation = validate_perception_payload(payload)
    payload["contract"] = validation
    return payload


def build_fallback_perception(image_path: str, source_type: str = "screenshot") -> dict[str, Any]:
    payload = {
        "source_type": source_type,
        "source_path": str(Path(image_path)),
        "ocr_text": "",
        "visual_summary": "",
        "detected_regions": [],
        "risk_signals": [],
        "confidence": "medium",
    }
    payload["contract"] = validate_perception_payload(payload)
    return payload


def _unwrap(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            import json

            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {"visual_summary": raw}
    return {}
