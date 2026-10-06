"""Persistence and transport handling for mq.review-receipt.v1.

mq-mcp owns receipt creation. mq-agent is only a consumer: it unwraps the MCP
transport, verifies the receipt's content address, and persists an ISSUED
receipt when the operator explicitly requested --receipt.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "mq.review-receipt.v1"
_RECEIPT_ID = re.compile(r"^sha256:([0-9a-f]{64})$")


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def unwrap_receipt(value: Any) -> dict[str, Any] | None:
    """Find one mq.review-receipt.v1 inside common MCP transport wrappers."""
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return unwrap_receipt(decoded)

    if isinstance(value, list):
        found = [receipt for item in value if (receipt := unwrap_receipt(item)) is not None]
        return found[0] if len(found) == 1 else None

    if not isinstance(value, dict):
        return None

    if value.get("schema") == SCHEMA:
        return value

    for key in ("result", "text", "content", "data"):
        if key not in value:
            continue
        receipt = unwrap_receipt(value[key])
        if receipt is not None:
            return receipt
    return None


def verify_receipt_id(receipt: dict[str, Any]) -> bool:
    """Verify mq-mcp's content address before this process stores the receipt."""
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or _RECEIPT_ID.fullmatch(receipt_id) is None:
        return False
    core = {key: value for key, value in receipt.items() if key != "receipt_id"}
    return receipt_id == _canonical_digest(core)


def review_result(receipt: dict[str, Any]) -> Any:
    """The underlying review result, kept separate from receipt metadata."""
    review = receipt.get("review")
    if not isinstance(review, dict) or "result" not in review:
        return None
    return review["result"]


def receipt_directory() -> Path:
    override = os.environ.get("MQ_AGENT_REVIEW_RECEIPTS_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".mq-agent" / "review-receipts"


def save_issued_receipt(
    receipt: dict[str, Any],
    *,
    directory: Path | None = None,
) -> Path:
    """Atomically persist one valid ISSUED receipt.

    REFUSED receipts are evidence failures, not reusable proof, and are never
    stored by this function.
    """
    if receipt.get("schema") != SCHEMA:
        raise ValueError(f"unexpected receipt schema: {receipt.get('schema')!r}")
    if receipt.get("status") != "ISSUED":
        raise ValueError("only ISSUED review receipts may be stored")
    if not verify_receipt_id(receipt):
        raise ValueError("review receipt content address is invalid")

    receipt_id = str(receipt["receipt_id"])
    match = _RECEIPT_ID.fullmatch(receipt_id)
    if match is None:  # defensive; verify_receipt_id already checked
        raise ValueError("invalid receipt id")

    target_dir = directory or receipt_directory()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{match.group(1)}.json"
    serialized = json.dumps(receipt, indent=2, ensure_ascii=False) + "\n"

    fd, tmp_name = tempfile.mkstemp(
        prefix=".review-receipt-",
        suffix=".tmp",
        dir=target_dir,
        text=True,
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return target
