"""Content-addressed Hybrid Retrieval v2 evidence collection.

The suite file is operator input and may contain raw queries and local paths.
Persisted evidence never stores those values: it keeps query/fixture hashes,
bounded metrics and references to content-addressed v2 run records only.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from mq_agent.memory.hybrid_retrieval import hybrid_retrieval_v2
from mq_agent.tools.contract_validation import validate_contract

SUITE_SCHEMA = "mq.hybrid-retrieval-suite.v1"
EVIDENCE_SCHEMA = "mq.hybrid-retrieval-evidence-set.v1"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(base: Path, value: str | None) -> Path | None:
    if not value:
        return None
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else (base / candidate).resolve()


def _metric_mean(cases: list[dict[str, Any]], field: str) -> float | None:
    values = [
        float(case["metrics"][field])
        for case in cases
        if case["metrics"].get(field) is not None
    ]
    return round(fmean(values), 6) if values else None


def _suite(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.expanduser().read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("hybrid retrieval suite must be a JSON object")
    validate_contract("hybrid_retrieval_suite.schema.json", value)
    case_ids = [str(item["id"]) for item in value["cases"]]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("hybrid retrieval suite case ids must be unique")
    return value, "sha256:" + hashlib.sha256(raw).hexdigest()


def _project_case(
    case: dict[str, Any],
    result: dict[str, Any],
    fixture_sha: str,
    run_fingerprint: str,
) -> dict[str, Any]:
    available = sorted(
        str(channel["name"])
        for channel in result["channels"]
        if channel["status"] == "AVAILABLE"
    )
    unavailable = sorted(
        str(channel["name"])
        for channel in result["channels"]
        if channel["status"] == "UNAVAILABLE"
    )
    skipped = sorted(
        str(channel["name"])
        for channel in result["channels"]
        if channel["status"] == "SKIPPED"
    )
    total_latency = round(
        sum(float(channel["latency_ms"]) for channel in result["channels"]),
        3,
    )
    metrics = result["metrics"]
    return {
        "case_id": case["id"],
        "task_class": case["task_class"],
        "query_sha256": result["query_sha256"],
        "fixture_sha256": fixture_sha,
        "run_fingerprint": run_fingerprint,
        "input_fingerprints": dict(result["input_fingerprints"]),
        "status": result["status"],
        "available_channels": available,
        "unavailable_channels": unavailable,
        "skipped_channels": skipped,
        "merged_result_count": result["merge"]["result_count"],
        "metrics": {
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "contradiction_rate": metrics["contradiction_rate"],
            "stale_rate": metrics["stale_rate"],
            "payload_token_estimate": metrics["payload_token_estimate"],
            "active_payload_token_estimate": metrics["active_payload_token_estimate"],
            "token_delta_vs_active": metrics["token_delta_vs_active"],
            "total_channel_latency_ms": total_latency,
        },
    }


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    channels: dict[str, dict[str, int]] = {}
    for case in cases:
        for name in case["available_channels"]:
            channels.setdefault(name, {"available": 0, "unavailable": 0, "skipped": 0})
            channels[name]["available"] += 1
        for name in case["unavailable_channels"]:
            channels.setdefault(name, {"available": 0, "unavailable": 0, "skipped": 0})
            channels[name]["unavailable"] += 1
        for name in case["skipped_channels"]:
            channels.setdefault(name, {"available": 0, "unavailable": 0, "skipped": 0})
            channels[name]["skipped"] += 1

    return {
        "case_count": len(cases),
        "task_class_count": len({str(case["task_class"]) for case in cases}),
        "pass_count": sum(case["status"] == "PASS" for case in cases),
        "insufficient_evidence_count": sum(
            case["status"] == "INSUFFICIENT_EVIDENCE" for case in cases
        ),
        "quality_measured_count": sum(
            case["metrics"]["precision"] is not None for case in cases
        ),
        "mean_precision": _metric_mean(cases, "precision"),
        "mean_recall": _metric_mean(cases, "recall"),
        "mean_contradiction_rate": _metric_mean(cases, "contradiction_rate"),
        "mean_stale_rate": _metric_mean(cases, "stale_rate"),
        "mean_token_delta_vs_active": _metric_mean(cases, "token_delta_vs_active"),
        "mean_total_channel_latency_ms": _metric_mean(
            cases, "total_channel_latency_ms"
        ),
        "channel_coverage": dict(sorted(channels.items())),
    }


class HybridEvidenceStore:
    """Immutable content-addressed local evidence store."""

    def __init__(self, root: Path | None = None):
        self.root = (
            root.expanduser()
            if root is not None
            else Path.home() / ".mq-agent" / "hybrid-retrieval"
        )

    def _path(self, kind: str, fingerprint: str) -> Path:
        prefix = "sha256:"
        if not fingerprint.startswith(prefix):
            raise ValueError("evidence fingerprint must use sha256:")
        digest = fingerprint[len(prefix):]
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("invalid evidence fingerprint")
        return self.root / kind / f"{digest}.json"

    def _write(self, path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if path.exists():
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"unsafe evidence store entry: {path.name}")
            if path.read_text(encoding="utf-8") != encoded:
                raise ValueError(f"content-addressed evidence collision: {path.name}")
            return
        path.write_text(encoded, encoding="utf-8")

    def save_run(self, result: dict[str, Any]) -> str:
        validate_contract("hybrid_retrieval_v2.schema.json", result)
        fingerprint = _fingerprint(result)
        self._write(self._path("runs", fingerprint), result)
        return fingerprint

    def save_set(self, evidence: dict[str, Any]) -> str:
        validate_contract("hybrid_retrieval_evidence.schema.json", evidence)
        fingerprint = evidence["evidence_id"]
        expected = _fingerprint({k: v for k, v in evidence.items() if k != "evidence_id"})
        if fingerprint != expected:
            raise ValueError("hybrid evidence id does not match content")
        self._write(self._path("sets", fingerprint), evidence)
        return fingerprint

    def verify_set(self, evidence_id: str) -> dict[str, Any]:
        path = self._path("sets", evidence_id)
        if not path.exists() or path.is_symlink() or not path.is_file():
            raise ValueError("hybrid evidence set not found")
        evidence = json.loads(path.read_text(encoding="utf-8"))
        validate_contract("hybrid_retrieval_evidence.schema.json", evidence)
        expected = _fingerprint({k: v for k, v in evidence.items() if k != "evidence_id"})
        errors: list[str] = []
        if evidence["evidence_id"] != evidence_id:
            errors.append("evidence set id/path mismatch")
        if expected != evidence_id:
            errors.append("evidence set content fingerprint mismatch")

        for case in evidence["cases"]:
            run_id = case["run_fingerprint"]
            run_path = self._path("runs", run_id)
            if not run_path.exists() or run_path.is_symlink() or not run_path.is_file():
                errors.append(f"{case['case_id']}: referenced run is missing")
                continue
            run = json.loads(run_path.read_text(encoding="utf-8"))
            try:
                validate_contract("hybrid_retrieval_v2.schema.json", run)
            except Exception:
                errors.append(f"{case['case_id']}: referenced run is invalid")
                continue
            if _fingerprint(run) != run_id:
                errors.append(f"{case['case_id']}: referenced run fingerprint mismatch")
            if run["query_sha256"] != case["query_sha256"]:
                errors.append(f"{case['case_id']}: query hash mismatch")
            case_inputs = case.get("input_fingerprints")
            if case_inputs is not None:
                run_inputs = run.get("input_fingerprints")
                if run_inputs is None:
                    errors.append(f"{case['case_id']}: run input fingerprints missing")
                elif run_inputs != case_inputs:
                    errors.append(f"{case['case_id']}: input fingerprint mismatch")
            if run["quality_evidence"]["fixture_sha256"] is None:
                errors.append(f"{case['case_id']}: fixture evidence is unavailable")
            elif "sha256:" + run["quality_evidence"]["fixture_sha256"] != case["fixture_sha256"]:
                errors.append(f"{case['case_id']}: fixture hash mismatch")

        return {
            "evidence_id": evidence_id,
            "status": "VERIFIED" if not errors else "REFUSED",
            "errors": errors,
            "evidence": evidence,
        }


def collect_hybrid_evidence(
    suite_path: Path,
    *,
    state_root: Path | None = None,
    persist: bool = True,
    active_search: Any = None,
    codegraph_search: Any = None,
) -> dict[str, Any]:
    """Run one fixture-backed zero-effect suite and optionally persist evidence."""
    suite_path = suite_path.expanduser().resolve()
    suite, suite_sha = _suite(suite_path)
    base = suite_path.parent
    store = HybridEvidenceStore(state_root)
    cases: list[dict[str, Any]] = []

    shared_catalog = _resolve(base, suite.get("catalog"))
    shared_semantic_index = _resolve(base, suite.get("semantic_index"))
    shared_codegraph_root = _resolve(base, suite.get("codegraph_root"))
    semantic_model = str(suite.get("semantic_model", "nomic-embed-text"))
    top_k = int(suite.get("top_k", 10))
    enable_codegraph = bool(suite.get("codegraph", True))

    for case in suite["cases"]:
        fixture_path = _resolve(base, str(case["fixture"]))
        if fixture_path is None:
            raise ValueError(f"{case['id']}: fixture is required")
        if not fixture_path.is_file():
            raise ValueError(f"{case['id']}: fixture file does not exist")
        fixture_sha = _file_sha256(fixture_path)

        result = hybrid_retrieval_v2(
            str(case["query"]),
            catalog_path=_resolve(base, case.get("catalog")) or shared_catalog,
            semantic_index_path=(
                _resolve(base, case.get("semantic_index")) or shared_semantic_index
            ),
            semantic_model=str(case.get("semantic_model") or semantic_model),
            fixture_path=fixture_path,
            codegraph_root=(
                _resolve(base, case.get("codegraph_root")) or shared_codegraph_root
            ),
            top_k=int(case.get("top_k") or top_k),
            enable_codegraph=bool(case.get("codegraph", enable_codegraph)),
            active_search=active_search,
            codegraph_search=codegraph_search,
        )
        run_fingerprint = _fingerprint(result)
        if persist:
            store.save_run(result)
        cases.append(_project_case(case, result, fixture_sha, run_fingerprint))

    aggregate = _aggregate(cases)
    status = (
        "PASS"
        if aggregate["pass_count"] == len(cases)
        and aggregate["quality_measured_count"] == len(cases)
        else "INSUFFICIENT_EVIDENCE"
    )
    payload: dict[str, Any] = {
        "schema": EVIDENCE_SCHEMA,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "suite_sha256": suite_sha,
        "status": status,
        "zero_effect": True,
        "promotion_eligible": False,
        "cases": cases,
        "aggregate": aggregate,
        "limitations": [
            "The suite records measurement evidence only; it cannot activate retrieval policy.",
            "Suite queries and local paths are input-only and are not persisted in evidence.",
            "Representativeness is an operator review question; mq-agent reports task-class coverage but does not invent a promotion threshold.",
        ],
    }
    payload["evidence_id"] = _fingerprint(payload)
    validate_contract("hybrid_retrieval_evidence.schema.json", payload)
    if persist:
        store.save_set(payload)
    return payload
