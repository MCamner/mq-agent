"""Small helper for validating mq-agent-owned packaged JSON contracts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def schema_path(filename: str) -> Path:
    packaged = Path(__file__).resolve().parents[1] / "schemas" / filename
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[2] / "schemas" / filename


def validate_contract(filename: str, payload: dict[str, Any]) -> None:
    schema = json.loads(schema_path(filename).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)
