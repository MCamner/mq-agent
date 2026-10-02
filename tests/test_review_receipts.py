"""Tests for mq-agent's review-receipt consumer."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mq_agent.core.review_receipts import (
    review_result,
    save_issued_receipt,
    unwrap_receipt,
    verify_receipt_id,
)


def _receipt(status: str = "ISSUED"):
    core = {
        "schema": "mq.review-receipt.v1",
        "status": status,
        "reason": "exact-subject-snapshot-stable" if status == "ISSUED" else "subject-changed-during-review",
        "started_at": "2026-10-02T12:00:00+00:00",
        "completed_at": "2026-10-02T12:00:01+00:00",
        "subject": {
            "repo": "demo",
            "commit": "a" * 40,
            "branch": "main",
            "worktree_clean": True,
            "scope": {"type": "file", "path": "a.py", "file_count": 1, "files": []},
            "snapshot_sha256": "sha256:" + "b" * 64,
        },
        "stability": {
            "before": "sha256:" + "b" * 64,
            "after": "sha256:" + "b" * 64,
            "unchanged": status == "ISSUED",
        },
        "producer": {"component": "mq-mcp", "commit": "c" * 40},
        "review": {
            "kind": "file",
            "mode": "comment",
            "result_sha256": "sha256:" + "d" * 64,
            "result": {"ok": True, "findings": []},
        },
    }
    raw = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {"receipt_id": "sha256:" + hashlib.sha256(raw).hexdigest(), **core}


@pytest.mark.parametrize(
    "wrapper",
    [
        lambda r: r,
        lambda r: json.dumps(r),
        lambda r: {"result": json.dumps(r)},
        lambda r: {"content": [{"type": "text", "text": json.dumps(r)}]},
        lambda r: [{"type": "text", "text": json.dumps(r)}],
    ],
)
def test_unwrap_receipt_accepts_common_mcp_shapes(wrapper):
    receipt = _receipt()
    assert unwrap_receipt(wrapper(receipt)) == receipt


def test_unwrap_receipt_refuses_ambiguous_multiple_receipts():
    receipt = _receipt()
    assert unwrap_receipt([receipt, receipt]) is None


def test_verify_receipt_id_detects_tampering():
    receipt = _receipt()
    assert verify_receipt_id(receipt) is True
    receipt["review"]["result"] = {"ok": False}
    assert verify_receipt_id(receipt) is False


def test_review_result_returns_only_review_payload():
    receipt = _receipt()
    assert review_result(receipt) == {"ok": True, "findings": []}


def test_save_issued_receipt_is_content_addressed(tmp_path):
    receipt = _receipt()
    path = save_issued_receipt(receipt, directory=tmp_path)
    assert path.name == receipt["receipt_id"].split(":", 1)[1] + ".json"
    assert json.loads(path.read_text()) == receipt


def test_save_is_idempotent_for_same_receipt(tmp_path):
    receipt = _receipt()
    first = save_issued_receipt(receipt, directory=tmp_path)
    second = save_issued_receipt(receipt, directory=tmp_path)
    assert first == second
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_refused_receipt_is_never_persisted(tmp_path):
    receipt = _receipt("REFUSED")
    with pytest.raises(ValueError, match="only ISSUED"):
        save_issued_receipt(receipt, directory=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_invalid_content_address_is_never_persisted(tmp_path):
    receipt = _receipt()
    receipt["receipt_id"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="content address"):
        save_issued_receipt(receipt, directory=tmp_path)
    assert list(tmp_path.iterdir()) == []
