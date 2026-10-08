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
ABLATION_SCHEMA = "mq.hybrid-retrieval-ablation.v1"
ADMISSION_SCHEMA = "mq.hybrid-retrieval-admission.v1"

ABLATION_MATRIX: tuple[tuple[str, dict[str, bool]], ...] = (
    ("keyword", {"notebook_keyword": True, "notebook_vector": False, "codegraph": False}),
    ("vector", {"notebook_keyword": False, "notebook_vector": True, "codegraph": False}),
    ("codegraph", {"notebook_keyword": False, "notebook_vector": False, "codegraph": True}),
    ("keyword+vector", {"notebook_keyword": True, "notebook_vector": True, "codegraph": False}),
    ("keyword+codegraph", {"notebook_keyword": True, "notebook_vector": False, "codegraph": True}),
    ("vector+codegraph", {"notebook_keyword": False, "notebook_vector": True, "codegraph": True}),
    ("all", {"notebook_keyword": True, "notebook_vector": True, "codegraph": True}),
)
ACTIVE_ONLY_SELECTION = {
    "notebook_keyword": False,
    "notebook_vector": False,
    "codegraph": False,
}
SINGLETON_ADMISSION_VARIANTS = {
    "notebook-keyword": "keyword",
    "notebook-vector": "vector",
    "codegraph": "codegraph",
}


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
        "channel_selection": dict(result["channel_selection"]),
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


def _ablation_metrics(aggregate: dict[str, Any]) -> dict[str, float | None]:
    return {
        "mean_precision": aggregate["mean_precision"],
        "mean_recall": aggregate["mean_recall"],
        "mean_contradiction_rate": aggregate["mean_contradiction_rate"],
        "mean_stale_rate": aggregate["mean_stale_rate"],
        "mean_token_delta_vs_active": aggregate["mean_token_delta_vs_active"],
        "mean_total_channel_latency_ms": aggregate["mean_total_channel_latency_ms"],
    }


def _ablation_summary(
    evidence: dict[str, Any],
    selection: dict[str, bool],
    *,
    variant_id: str | None = None,
) -> dict[str, Any]:
    aggregate = evidence["aggregate"]
    summary: dict[str, Any] = {
        "evidence_id": evidence["evidence_id"],
        "status": evidence["status"],
        "channel_selection": dict(selection),
        "case_count": aggregate["case_count"],
        "pass_count": aggregate["pass_count"],
        "quality_measured_count": aggregate["quality_measured_count"],
        "metrics": _ablation_metrics(aggregate),
        "channel_coverage": aggregate["channel_coverage"],
    }
    if variant_id is not None:
        summary["variant_id"] = variant_id
    return summary


def _metric_delta(
    current: dict[str, float | None],
    baseline: dict[str, float | None],
) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for field in current:
        left = current[field]
        right = baseline[field]
        result[field] = (
            round(float(left) - float(right), 6)
            if left is not None and right is not None
            else None
        )
    return result


def _admission_case_delta(
    baseline: dict[str, Any],
    variant: dict[str, Any],
) -> dict[str, float | None]:
    fields = (
        "precision",
        "recall",
        "contradiction_rate",
        "stale_rate",
        "token_delta_vs_active",
        "total_channel_latency_ms",
    )
    result: dict[str, float | None] = {}
    for field in fields:
        left = variant["metrics"].get(field)
        right = baseline["metrics"].get(field)
        result[field] = (
            round(float(left) - float(right), 6)
            if left is not None and right is not None
            else None
        )
    return result


def _admission_case_result(
    baseline: dict[str, Any],
    variant: dict[str, Any],
) -> dict[str, Any]:
    delta = _admission_case_delta(baseline, variant)
    quality = {
        key: delta[key]
        for key in ("precision", "recall", "contradiction_rate", "stale_rate")
    }
    if any(value is None for value in quality.values()):
        status = "INSUFFICIENT_EVIDENCE"
        regressions: list[str] = []
        gains: list[str] = []
    else:
        regressions = [
            name
            for name, value in quality.items()
            if (
                value is not None
                and (
                    value < 0
                    if name in {"precision", "recall"}
                    else value > 0
                )
            )
        ]
        gains = [
            name
            for name, value in quality.items()
            if (
                value is not None
                and (
                    value > 0
                    if name in {"precision", "recall"}
                    else value < 0
                )
            )
        ]
        if regressions:
            status = "BLOCKS_ADMISSION"
        elif gains:
            status = "SUPPORTS_ADMISSION"
        else:
            status = "NEUTRAL"

    return {
        "case_id": baseline["case_id"],
        "baseline_run_fingerprint": baseline["run_fingerprint"],
        "variant_run_fingerprint": variant["run_fingerprint"],
        "status": status,
        "quality_gains": sorted(gains),
        "quality_regressions": sorted(regressions),
        "delta_vs_active_only": delta,
    }


def _admission_delta_mean(
    case_results: list[dict[str, Any]],
) -> dict[str, float | None]:
    fields = (
        "precision",
        "recall",
        "contradiction_rate",
        "stale_rate",
        "token_delta_vs_active",
        "total_channel_latency_ms",
    )
    result: dict[str, float | None] = {}
    for field in fields:
        values = [
            float(item["delta_vs_active_only"][field])
            for item in case_results
            if item["delta_vs_active_only"].get(field) is not None
        ]
        result[field] = round(fmean(values), 6) if values else None
    return result


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

    def save_ablation(self, ablation: dict[str, Any]) -> str:
        validate_contract("hybrid_retrieval_ablation.schema.json", ablation)
        fingerprint = ablation["ablation_id"]
        expected = _fingerprint(
            {k: v for k, v in ablation.items() if k != "ablation_id"}
        )
        if fingerprint != expected:
            raise ValueError("hybrid ablation id does not match content")
        self._write(self._path("ablations", fingerprint), ablation)
        return fingerprint

    def save_admission(self, admission: dict[str, Any]) -> str:
        validate_contract("hybrid_retrieval_admission.schema.json", admission)
        fingerprint = admission["admission_id"]
        expected = _fingerprint(
            {k: v for k, v in admission.items() if k != "admission_id"}
        )
        if fingerprint != expected:
            raise ValueError("hybrid admission id does not match content")
        self._write(self._path("admissions", fingerprint), admission)
        return fingerprint

    def verify_admission(self, admission_id: str) -> dict[str, Any]:
        path = self._path("admissions", admission_id)
        if not path.exists() or path.is_symlink() or not path.is_file():
            raise ValueError("hybrid admission record not found")
        admission = json.loads(path.read_text(encoding="utf-8"))
        validate_contract("hybrid_retrieval_admission.schema.json", admission)
        expected_id = _fingerprint(
            {k: v for k, v in admission.items() if k != "admission_id"}
        )
        errors: list[str] = []
        if admission["admission_id"] != admission_id:
            errors.append("admission id/path mismatch")
        if expected_id != admission_id:
            errors.append("admission content fingerprint mismatch")

        try:
            expected = _build_hybrid_admission(
                admission["ablation_id"],
                self,
                created_at=admission["created_at"],
            )
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"admission evidence rebuild failed: {exc}")
        else:
            if expected != admission:
                errors.append("admission content does not match verified evidence")

        return {
            "admission_id": admission_id,
            "status": "VERIFIED" if not errors else "REFUSED",
            "errors": errors,
            "admission": admission,
        }

    def verify_ablation(self, ablation_id: str) -> dict[str, Any]:
        path = self._path("ablations", ablation_id)
        if not path.exists() or path.is_symlink() or not path.is_file():
            raise ValueError("hybrid ablation set not found")
        ablation = json.loads(path.read_text(encoding="utf-8"))
        validate_contract("hybrid_retrieval_ablation.schema.json", ablation)
        expected = _fingerprint(
            {k: v for k, v in ablation.items() if k != "ablation_id"}
        )
        errors: list[str] = []
        if ablation["ablation_id"] != ablation_id:
            errors.append("ablation id/path mismatch")
        if expected != ablation_id:
            errors.append("ablation content fingerprint mismatch")

        entries = [("baseline", ablation["baseline"])] + [
            (str(item["variant_id"]), item) for item in ablation["variants"]
        ]
        for label, entry in entries:
            verified = self.verify_set(str(entry["evidence_id"]))
            if verified["status"] != "VERIFIED":
                errors.append(f"{label}: referenced evidence is not verified")
                continue
            evidence = verified["evidence"]
            if evidence["suite_sha256"] != ablation["suite_sha256"]:
                errors.append(f"{label}: suite fingerprint mismatch")
            selection = entry["channel_selection"]
            if any(
                case.get("channel_selection") != selection
                for case in evidence["cases"]
            ):
                errors.append(f"{label}: channel selection mismatch")
            expected_summary = _ablation_summary(
                evidence,
                selection,
                variant_id=None if label == "baseline" else label,
            )
            if label != "baseline":
                baseline_metrics = ablation["baseline"]["metrics"]
                expected_summary["delta_vs_baseline"] = _metric_delta(
                    expected_summary["metrics"],
                    baseline_metrics,
                )
            if expected_summary != entry:
                errors.append(f"{label}: summary does not match referenced evidence")

        return {
            "ablation_id": ablation_id,
            "status": "VERIFIED" if not errors else "REFUSED",
            "errors": errors,
            "ablation": ablation,
        }

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
            case_selection = case.get("channel_selection")
            if case_selection is not None:
                run_selection = run.get("channel_selection")
                if run_selection is None:
                    errors.append(f"{case['case_id']}: run channel selection missing")
                elif run_selection != case_selection:
                    errors.append(f"{case['case_id']}: channel selection mismatch")
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
    channel_override: dict[str, bool] | None = None,
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
    shared_selection = {
        "notebook_keyword": bool(suite.get("notebook_keyword", True)),
        "notebook_vector": bool(suite.get("notebook_vector", True)),
        "codegraph": bool(suite.get("codegraph", True)),
    }

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
            enable_notebook_keyword=(
                channel_override["notebook_keyword"]
                if channel_override is not None
                else bool(case.get("notebook_keyword", shared_selection["notebook_keyword"]))
            ),
            enable_notebook_vector=(
                channel_override["notebook_vector"]
                if channel_override is not None
                else bool(case.get("notebook_vector", shared_selection["notebook_vector"]))
            ),
            enable_codegraph=(
                channel_override["codegraph"]
                if channel_override is not None
                else bool(case.get("codegraph", shared_selection["codegraph"]))
            ),
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


def collect_hybrid_ablation(
    suite_path: Path,
    *,
    state_root: Path | None = None,
    persist: bool = True,
    active_search: Any = None,
    codegraph_search: Any = None,
) -> dict[str, Any]:
    """Measure the fixed optional-channel ablation matrix over one unchanged suite."""
    suite_path = suite_path.expanduser().resolve()
    _suite_value, suite_sha = _suite(suite_path)
    store = HybridEvidenceStore(state_root)

    baseline_evidence = collect_hybrid_evidence(
        suite_path,
        state_root=state_root,
        persist=persist,
        active_search=active_search,
        codegraph_search=codegraph_search,
        channel_override=ACTIVE_ONLY_SELECTION,
    )
    baseline = _ablation_summary(
        baseline_evidence,
        ACTIVE_ONLY_SELECTION,
    )
    baseline_metrics = baseline["metrics"]

    variants: list[dict[str, Any]] = []
    for variant_id, selection in ABLATION_MATRIX:
        evidence = collect_hybrid_evidence(
            suite_path,
            state_root=state_root,
            persist=persist,
            active_search=active_search,
            codegraph_search=codegraph_search,
            channel_override=selection,
        )
        summary = _ablation_summary(
            evidence,
            selection,
            variant_id=variant_id,
        )
        summary["delta_vs_baseline"] = _metric_delta(
            summary["metrics"],
            baseline_metrics,
        )
        variants.append(summary)

    case_count = int(baseline["case_count"])
    complete_baseline = baseline["quality_measured_count"] == case_count
    complete_variants = all(
        item["status"] == "PASS"
        and item["quality_measured_count"] == item["case_count"]
        for item in variants
    )
    payload: dict[str, Any] = {
        "schema": ABLATION_SCHEMA,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "suite_sha256": suite_sha,
        "status": (
            "PASS"
            if complete_baseline and complete_variants
            else "INSUFFICIENT_EVIDENCE"
        ),
        "zero_effect": True,
        "promotion_eligible": False,
        "baseline": baseline,
        "variants": variants,
        "limitations": [
            "Ablation is zero-effect measurement only; active semantic memory remains authoritative.",
            "The baseline intentionally disables every optional channel and may be INSUFFICIENT_EVIDENCE as a Hybrid Retrieval run while still providing measured fixture metrics.",
            "Variant deltas compare aggregate measured metrics with the active-only baseline; they do not authorize RRF tuning or promotion.",
            "Suite queries and local paths remain input-only and are not persisted in the ablation record.",
        ],
    }
    payload["ablation_id"] = _fingerprint(payload)
    validate_contract("hybrid_retrieval_ablation.schema.json", payload)
    if persist:
        store.save_ablation(payload)
    return payload


def _build_hybrid_admission(
    ablation_id: str,
    store: HybridEvidenceStore,
    *,
    created_at: str,
) -> dict[str, Any]:
    verified_ablation = store.verify_ablation(ablation_id)
    if verified_ablation["status"] != "VERIFIED":
        raise ValueError("hybrid ablation must verify before admission evaluation")
    ablation = verified_ablation["ablation"]

    baseline_verified = store.verify_set(ablation["baseline"]["evidence_id"])
    if baseline_verified["status"] != "VERIFIED":
        raise ValueError("active-only baseline evidence must verify")
    baseline_evidence = baseline_verified["evidence"]
    baseline_by_case = {
        str(case["case_id"]): case for case in baseline_evidence["cases"]
    }

    variants = {
        str(item["variant_id"]): item
        for item in ablation["variants"]
    }
    singleton_evidence: dict[str, dict[str, Any]] = {}
    for channel, variant_id in SINGLETON_ADMISSION_VARIANTS.items():
        entry = variants.get(variant_id)
        if entry is None:
            raise ValueError(f"ablation singleton variant missing: {variant_id}")
        verified = store.verify_set(str(entry["evidence_id"]))
        if verified["status"] != "VERIFIED":
            raise ValueError(f"{variant_id}: singleton evidence must verify")
        singleton_evidence[channel] = verified["evidence"]

    task_classes = sorted(
        {str(case["task_class"]) for case in baseline_evidence["cases"]}
    )
    task_results: list[dict[str, Any]] = []
    evidence_complete = True

    for task_class in task_classes:
        baseline_cases = [
            case
            for case in baseline_evidence["cases"]
            if str(case["task_class"]) == task_class
        ]
        baseline_ids = {str(case["case_id"]) for case in baseline_cases}
        channel_results: list[dict[str, Any]] = []

        for channel, variant_id in SINGLETON_ADMISSION_VARIANTS.items():
            variant_evidence = singleton_evidence[channel]
            variant_by_case = {
                str(case["case_id"]): case
                for case in variant_evidence["cases"]
                if str(case["task_class"]) == task_class
            }
            variant_ids = set(variant_by_case)
            if variant_ids != baseline_ids:
                raise ValueError(
                    f"{task_class}/{channel}: singleton case identity mismatch"
                )

            case_results = [
                _admission_case_result(
                    baseline_by_case[case_id],
                    variant_by_case[case_id],
                )
                for case_id in sorted(baseline_ids)
            ]
            statuses = {str(item["status"]) for item in case_results}
            if "INSUFFICIENT_EVIDENCE" in statuses:
                decision = "INSUFFICIENT_EVIDENCE"
                reason = "quality metrics are incomplete"
                evidence_complete = False
            elif "BLOCKS_ADMISSION" in statuses:
                decision = "ACTIVE_ONLY"
                reason = "singleton channel regresses measured quality"
            elif "SUPPORTS_ADMISSION" in statuses:
                decision = "ELIGIBLE"
                reason = "measured quality gain with no measured quality regression"
            else:
                decision = "ACTIVE_ONLY"
                reason = "no measured quality gain"

            channel_results.append(
                {
                    "channel": channel,
                    "variant_id": variant_id,
                    "decision": decision,
                    "reason": reason,
                    "baseline_evidence_id": baseline_evidence["evidence_id"],
                    "variant_evidence_id": variant_evidence["evidence_id"],
                    "case_count": len(case_results),
                    "mean_delta_vs_active_only": _admission_delta_mean(case_results),
                    "cases": case_results,
                }
            )

        eligible = sorted(
            item["channel"]
            for item in channel_results
            if item["decision"] == "ELIGIBLE"
        )
        insufficient = any(
            item["decision"] == "INSUFFICIENT_EVIDENCE"
            for item in channel_results
        )
        task_results.append(
            {
                "task_class": task_class,
                "decision": (
                    "INSUFFICIENT_EVIDENCE"
                    if insufficient
                    else "OPTIONAL_CHANNELS_ELIGIBLE"
                    if eligible
                    else "ACTIVE_ONLY"
                ),
                "eligible_channels": eligible,
                "channels": channel_results,
            }
        )

    any_eligible = any(item["eligible_channels"] for item in task_results)
    status = "PASS" if evidence_complete else "INSUFFICIENT_EVIDENCE"
    decision = (
        "INSUFFICIENT_EVIDENCE"
        if not evidence_complete
        else "OPTIONAL_CHANNELS_ELIGIBLE"
        if any_eligible
        else "ACTIVE_ONLY"
    )
    payload: dict[str, Any] = {
        "schema": ADMISSION_SCHEMA,
        "created_at": created_at,
        "ablation_id": ablation_id,
        "suite_sha256": ablation["suite_sha256"],
        "status": status,
        "decision": decision,
        "zero_effect": True,
        "promotion_eligible": False,
        "activation_available": False,
        "human_approval_required": True,
        "task_classes": task_results,
        "requirements": [
            {
                "id": "verified-ablation",
                "status": "PASS",
                "detail": "referenced ablation and all underlying evidence verified",
            },
            {
                "id": "singleton-case-identity",
                "status": "PASS",
                "detail": "active-only and singleton variants use identical case ids per task class",
            },
            {
                "id": "quality-complete",
                "status": "PASS" if evidence_complete else "FAIL",
                "detail": (
                    "precision, recall, contradiction and stale metrics are complete"
                    if evidence_complete
                    else "one or more singleton comparisons lack complete quality metrics"
                ),
            },
            {
                "id": "no-invented-cost-threshold",
                "status": "PASS",
                "detail": "token and latency deltas are reported but do not gate admission without an explicit budget policy",
            },
        ],
        "next_action": (
            "collect-more-evidence"
            if not evidence_complete
            else "review-eligible-channels"
            if any_eligible
            else "keep-active-only"
        ),
        "limitations": [
            "This gate is read-only evidence evaluation; it does not alter Hybrid Retrieval channel selection.",
            "A channel is eligible only when singleton evidence shows at least one measured quality gain and no measured precision, recall, contradiction or stale regression within the task class.",
            "Token and latency costs are reported for operator review but no budget threshold is invented.",
            "Eligibility is not activation; runtime policy remains unchanged and human approval is still required.",
        ],
    }
    payload["admission_id"] = _fingerprint(payload)
    validate_contract("hybrid_retrieval_admission.schema.json", payload)
    return payload


def evaluate_hybrid_admission(
    ablation_id: str,
    *,
    state_root: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Evaluate one verified ablation into a read-only task-class admission gate."""
    store = HybridEvidenceStore(state_root)
    payload = _build_hybrid_admission(
        ablation_id,
        store,
        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    if persist:
        store.save_admission(payload)
    return payload
