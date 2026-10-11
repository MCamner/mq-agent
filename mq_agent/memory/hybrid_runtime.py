"""Receipt-bound Hybrid Retrieval approval and explicit reference consumption.

mq-agent owns these local contracts. The initial scope is repo-review/keyword.
Callers supply an observed runtime revision; each consumer must observe it
independently rather than reading it from the receipt.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import os
import subprocess
import sys
import time
from typing import Any

from jsonschema.exceptions import ValidationError

from mq_agent.memory.hybrid_evidence import (
    HybridEvidenceStore,
    _fingerprint,
    review_hybrid_policy_proposals,
)
from mq_agent.tools.contract_validation import validate_contract

_ERRORS = (OSError, RuntimeError, ValueError, ValidationError)


def _now(value: datetime | None) -> datetime:
    value = value or datetime.now(UTC)
    if value.utcoffset() is None:
        raise ValueError("time must be timezone-aware")
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _reason(value: str) -> str:
    if not value.strip() or len(value) > 320:
        raise ValueError("reason must contain 1 to 320 characters")
    return value.strip()


def _read_approval(store: HybridEvidenceStore, approval_id: str) -> dict[str, Any]:
    path = store._path("approvals", approval_id)
    if path.is_symlink() or not path.is_file():
        raise ValueError("approval not found or unsafe")
    record = json.loads(path.read_text(encoding="utf-8"))
    validate_contract("hybrid_retrieval_approval.schema.json", record)
    identity = _fingerprint({k: v for k, v in record.items() if k != "approval_id"})
    if record["approval_id"] != approval_id or identity != approval_id:
        raise ValueError("approval content fingerprint mismatch")
    approved = _now(
        datetime.fromisoformat(record["approved_at"].replace("Z", "+00:00"))
    )
    expires = _now(datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00")))
    if expires <= approved:
        raise ValueError("approval expiry must follow approval time")
    return record


def _check_revocation(store: HybridEvidenceStore, approval_id: str) -> None:
    # One immutable revocation per exact receipt, addressed by its target id.
    path = store._path("approval-revocations", approval_id)
    if path.is_symlink():
        raise ValueError("unsafe revocation entry")
    if not path.exists():
        return
    if not path.is_file():
        raise ValueError("unsafe revocation entry")
    record = json.loads(path.read_text(encoding="utf-8"))
    validate_contract("hybrid_retrieval_revocation.schema.json", record)
    identity = _fingerprint({k: v for k, v in record.items() if k != "revocation_id"})
    if record["approval_id"] != approval_id or record["revocation_id"] != identity:
        raise ValueError("revocation content fingerprint mismatch")
    _now(datetime.fromisoformat(record["revoked_at"].replace("Z", "+00:00")))
    raise ValueError("approval already revoked")


def _binding(
    store: HybridEvidenceStore,
    policy_plan_id: str,
    challenge_id: str,
    task_class: str,
    channel: str,
    catalog_path: Path,
) -> dict[str, Any]:
    if (task_class, channel) != ("repo-review", "notebook-keyword"):
        raise ValueError("initial approval scope is repo-review/notebook-keyword")
    verified = store.verify_policy_plan(policy_plan_id)
    if verified["status"] != "VERIFIED":
        raise ValueError("policy plan is not VERIFIED")
    plan = verified["policy_plan"]
    review = review_hybrid_policy_proposals(
        [policy_plan_id],
        admission_id=plan["admission_id"],
        challenge_id=challenge_id,
        expected_task_classes=[task_class],
        state_root=store.root,
    )
    if review["status"] != "VERIFIED":
        raise ValueError("proposal review refused: " + "; ".join(review["errors"]))
    if channel not in plan["eligible_channels"]:
        raise ValueError("selected channel is not eligible")
    admission = store.verify_admission(plan["admission_id"])["admission"]
    task = next(
        row for row in admission["task_classes"] if row["task_class"] == task_class
    )
    channel_row = next(row for row in task["channels"] if row["channel"] == channel)
    evidence = store.verify_set(channel_row["variant_evidence_id"])
    if evidence["status"] != "VERIFIED":
        raise ValueError("singleton evidence is not VERIFIED")
    for case in evidence["evidence"]["cases"]:
        if case["task_class"] == task_class:
            run = json.loads(
                store._path("runs", case["run_fingerprint"]).read_text(encoding="utf-8")
            )
            if run["top_k"] != 10:
                raise ValueError("consumer requires measured top-k=10")
    fingerprints = {
        case.get("input_fingerprints", {}).get("notebook_catalog_sha256")
        for case in evidence["evidence"]["cases"]
        if case["task_class"] == task_class
    }
    current = "sha256:" + hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    if fingerprints != {current}:
        raise ValueError("catalog does not match measured singleton evidence")
    return {
        "policy_plan_id": policy_plan_id,
        "admission_id": plan["admission_id"],
        "challenge_id": challenge_id,
        "ablation_id": admission["ablation_id"],
        "suite_sha256": admission["suite_sha256"],
        "proposal_review_fingerprint": _fingerprint(review),
        "input_fingerprints": {"notebook_catalog_sha256": current},
    }


def approve_hybrid_policy(
    policy_plan_id: str,
    *,
    challenge_id: str,
    task_class: str,
    channel: str,
    catalog_path: Path,
    runtime_revision: str,
    max_additional_tokens: int,
    optional_timeout_ms: int,
    validity_seconds: int,
    reason: str,
    approve: bool = False,
    state_root: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist explicit single-channel approval, never activate retrieval."""
    if approve is not True:
        raise ValueError("explicit approval is required")
    for name, value in [
        ("max_additional_tokens", max_additional_tokens),
        ("optional_timeout_ms", optional_timeout_ms),
        ("validity_seconds", validity_seconds),
    ]:
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if not re.fullmatch("[0-9a-f]{40}", runtime_revision):
        raise ValueError("runtime_revision must be an exact Git commit")
    reason = _reason(reason)
    timestamp = _now(now)
    try:
        expires = timestamp + timedelta(seconds=validity_seconds)
    except OverflowError as exc:
        raise ValueError("validity_seconds exceeds supported time range") from exc
    store = HybridEvidenceStore(state_root)
    try:
        binding = _binding(
            store, policy_plan_id, challenge_id, task_class, channel, catalog_path
        )
    except _ERRORS as exc:
        raise ValueError(str(exc)) from exc
    record = {
        "schema": "mq.hybrid-retrieval-approval.v1",
        **binding,
        "task_class": task_class,
        "channel": channel,
        "runtime_revision": runtime_revision,
        "budget": {
            "max_additional_tokens": max_additional_tokens,
            "optional_timeout_ms": optional_timeout_ms,
            "token_measurement": "additional-json-chars-div-4",
        },
        "approved_at": _iso(timestamp),
        "expires_at": _iso(expires),
        "reason": reason,
        "runtime_consumption_available": False,
    }
    record["approval_id"] = _fingerprint(record)
    validate_contract("hybrid_retrieval_approval.schema.json", record)
    _check_revocation(store, record["approval_id"])
    store._write(store._path("approvals", record["approval_id"]), record)
    return record


def verify_hybrid_approval(
    approval_id: str,
    *,
    task_class: str,
    channel: str,
    catalog_path: Path,
    runtime_revision: str,
    state_root: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Re-verify evidence, expiry, revocation and independently supplied live inputs."""
    errors = []
    record = None
    try:
        store = HybridEvidenceStore(state_root)
        record = _read_approval(store, approval_id)
        _check_revocation(store, approval_id)
        timestamp = _now(now)
        approved = datetime.fromisoformat(record["approved_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
        if not approved <= timestamp < expires:
            raise ValueError("approval expired or not yet valid")
        if (task_class, channel, runtime_revision) != (
            record["task_class"],
            record["channel"],
            record["runtime_revision"],
        ):
            raise ValueError("approval scope or runtime revision mismatch")
        binding = _binding(
            store,
            record["policy_plan_id"],
            record["challenge_id"],
            task_class,
            channel,
            catalog_path,
        )
        if any(record[key] != value for key, value in binding.items()):
            raise ValueError("approval evidence binding mismatch")
    except _ERRORS as exc:
        errors.append(str(exc))
    return {
        "approval_id": approval_id,
        "status": "REFUSED" if errors else "VERIFIED",
        "errors": errors,
        "approval": record,
        "runtime_consumption_available": False,
    }


def revoke_hybrid_approval(
    approval_id: str,
    *,
    reason: str,
    approve: bool = False,
    state_root: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append a revocation for one exact receipt, retaining its original bytes."""
    if approve is not True:
        raise ValueError("explicit approval is required")
    reason = _reason(reason)
    store = HybridEvidenceStore(state_root)
    try:
        _read_approval(store, approval_id)
        _check_revocation(store, approval_id)
    except _ERRORS as exc:
        raise ValueError(str(exc)) from exc
    record = {
        "schema": "mq.hybrid-retrieval-revocation.v1",
        "approval_id": approval_id,
        "revoked_at": _iso(_now(now)),
        "reason": reason,
    }
    record["revocation_id"] = _fingerprint(record)
    validate_contract("hybrid_retrieval_revocation.schema.json", record)
    store._write(store._path("approval-revocations", approval_id), record)
    return record


def _keyword_worker() -> None:
    """Search an in-memory catalog snapshot; never persist query or content."""
    from mq_agent.memory.hybrid_retrieval import _notebook_refs
    from mq_agent.notebook_corpus_search import search_catalog

    query = json.loads(sys.stdin.buffer.readline())
    catalog = json.load(sys.stdin.buffer)
    result = search_catalog(catalog, query, top_k=10)
    json.dump(_notebook_refs(result["results"]), sys.stdout, ensure_ascii=False)


def _keyword_search(
    catalog: bytes, query: str, timeout_ms: float
) -> list[dict[str, str]]:
    # communicate() kills and reaps the child on timeout; no lingering thread.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from mq_agent.memory.hybrid_runtime import _keyword_worker; _keyword_worker()",
        ],
        input=json.dumps(query, ensure_ascii=False).encode("utf-8") + b"\n" + catalog,
        capture_output=True,
        check=True,
        timeout=timeout_ms / 1000,
    )
    refs = json.loads(result.stdout)
    if not isinstance(refs, list) or any(
        not isinstance(row, dict)
        or set(row) != {"namespace", "reference"}
        or row["namespace"] != "notebook"
        or not isinstance(row["reference"], str)
        or not row["reference"]
        for row in refs
    ):
        raise ValueError("invalid optional references")
    return refs


def retrieve_hybrid_memory(
    query: str,
    *,
    task_class: str = "repo-review",
    approval_id: str | None = None,
    catalog_path: Path | None = None,
    runtime_revision: str | None = None,
    state_root: Path | None = None,
    now: datetime | None = None,
    active_search: Any = None,
) -> dict[str, Any]:
    """Explicit receipt-bound reference retrieval; failures retain active-only."""
    from mq_agent.memory.hybrid_retrieval import (
        _active_refs,
        _default_active_search,
        _rrf,
        _run_channel,
    )

    if not query.strip():
        raise ValueError("query must not be empty")
    trace: dict[str, Any] = {
        "query_sha256": _fingerprint(query),
        "approval_id": approval_id,
        "task_class": task_class,
        "runtime_revision": runtime_revision,
        "effective_channel_selection": {
            "notebook_keyword": False,
            "notebook_vector": False,
            "codegraph": False,
        },
        "fallback_reason": None,
        "additional_token_estimate": None,
        "optional_latency_ms": None,
    }
    output: dict[str, Any] = {
        "status": "PASS",
        "mode": "ACTIVE_ONLY",
        "active_result": None,
        "refs": [],
        "trace": trace,
    }
    try:
        raw = (active_search or _default_active_search)(query)
        output["active_result"] = raw
        if raw is None:
            raise ValueError("active search returned no response")
        active, active_refs = _run_channel(
            "mq-mcp-semantic",
            "vector",
            lambda: raw,
            _active_refs,
        )
        if active["status"] != "AVAILABLE":
            raise ValueError("active search unavailable")
    except (OSError, RuntimeError, ValueError):
        output["status"] = "UNAVAILABLE"
        trace["fallback_reason"] = "active-unavailable"
        return output
    output["refs"] = _rrf([("mq-mcp-semantic", active_refs)], 10)
    if not approval_id:
        return output
    if os.environ.get("MQ_HYBRID_CONSUMPTION", "on").lower() != "on":
        trace["fallback_reason"] = "consumption-disabled"
        return output
    if task_class != "repo-review" or catalog_path is None or runtime_revision is None:
        trace["fallback_reason"] = "approval-scope-unavailable"
        return output
    verification = verify_hybrid_approval(
        approval_id,
        task_class=task_class,
        channel="notebook-keyword",
        catalog_path=catalog_path,
        runtime_revision=runtime_revision,
        state_root=state_root,
        now=now,
    )
    if verification["status"] != "VERIFIED":
        trace["fallback_reason"] = "approval-refused"
        return output
    receipt = verification["approval"]
    for key in (
        "policy_plan_id",
        "admission_id",
        "challenge_id",
        "ablation_id",
        "suite_sha256",
    ):
        trace[key] = receipt[key]
    trace["budget"] = receipt["budget"]
    trace["input_fingerprints"] = receipt["input_fingerprints"]
    started = time.monotonic()
    try:
        snapshot = catalog_path.read_bytes()
        fingerprint = "sha256:" + hashlib.sha256(snapshot).hexdigest()
        if fingerprint != receipt["input_fingerprints"]["notebook_catalog_sha256"]:
            trace["fallback_reason"] = "catalog-changed"
            return output
        remaining_ms = (
            receipt["budget"]["optional_timeout_ms"]
            - (time.monotonic() - started) * 1000
        )
        if remaining_ms <= 0:
            raise subprocess.TimeoutExpired("keyword worker", 0)
        optional_refs = _keyword_search(snapshot, query, remaining_ms)
        elapsed = (time.monotonic() - started) * 1000
        trace["optional_latency_ms"] = round(elapsed, 3)
        if elapsed > receipt["budget"]["optional_timeout_ms"]:
            trace["fallback_reason"] = "optional-timeout"
            return output
        serialized = json.dumps(
            optional_refs, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        trace["additional_token_estimate"] = (len(serialized) + 3) // 4
        if (
            trace["additional_token_estimate"]
            > receipt["budget"]["max_additional_tokens"]
        ):
            trace["fallback_reason"] = "optional-budget-exceeded"
            return output
        # Recheck expiry/revocation and catalog after the child completes.
        checked = verify_hybrid_approval(
            approval_id,
            task_class=task_class,
            channel="notebook-keyword",
            catalog_path=catalog_path,
            runtime_revision=runtime_revision,
            state_root=state_root,
            now=now,
        )
        if checked["status"] != "VERIFIED":
            trace["fallback_reason"] = "approval-refused"
            return output
        if os.environ.get("MQ_HYBRID_CONSUMPTION", "on").lower() != "on":
            trace["fallback_reason"] = "consumption-disabled"
            return output
        if not optional_refs:
            trace["fallback_reason"] = "optional-no-results"
            return output
        output["refs"] = _rrf(
            [("mq-mcp-semantic", active_refs), ("notebook-keyword", optional_refs)], 10
        )
        output["mode"] = "HYBRID"
        trace["effective_channel_selection"]["notebook_keyword"] = True
    except subprocess.TimeoutExpired:
        trace["optional_latency_ms"] = round((time.monotonic() - started) * 1000, 3)
        trace["fallback_reason"] = "optional-timeout"
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        trace["fallback_reason"] = "optional-unavailable"
    return output
