"""Cross-notebook research over D5 evidence bundles.

D6 may synthesize only after D5 has produced bounded, provenance-bearing
material. Model output is treated as a proposal: source authority, independence
and cross-notebook support are re-validated deterministically before a finding
is accepted.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from mq_agent.notebook_corpus_retrieval import SelectiveTextProvider, retrieve_evidence
from mq_agent.tools.model_runtime import current_model

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"


class ResearchSynthesizer(Protocol):
    def synthesize(
        self,
        question: str,
        evidence: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]: ...


class OllamaResearchSynthesizer:
    """Local JSON synthesizer. Authority is validated after generation."""

    def __init__(
        self,
        *,
        model: str | None = None,
        timeout: int = 60,
        host: str | None = None,
    ) -> None:
        selected = model or str(current_model()["model"])
        if not selected:
            raise ValueError("no research model configured")
        self.model = selected
        self.timeout = timeout
        configured = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST).strip()
        if "://" not in configured:
            configured = f"http://{configured}"
        self.host = configured.rstrip("/")

    def synthesize(
        self,
        question: str,
        evidence: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        compact = []
        for item in evidence:
            prov = item["provenance"]
            compact.append(
                {
                    "drive_item_id": prov["drive_item_id"],
                    "notebook_id": prov["notebook_id"],
                    "notebook_title": prov["notebook_title"],
                    "title": prov["title"],
                    "source_role": prov["source_role"],
                    "claim_eligible": bool(item["claim_eligible"]),
                    "excerpt": item["excerpt"],
                }
            )

        prompt = (
            "You are proposing a research synthesis over supplied evidence. "
            "Do not invent evidence ids. Do not treat derived material as source proof. "
            "Return exactly one JSON object with keys common_findings, disagreements, "
            "derived_interpretations, unanswered_questions. "
            "common_findings must be a list of objects with claim and supporting_drive_item_ids. "
            "disagreements must be a list of objects with topic and positions, where each "
            "position has claim and supporting_drive_item_ids. "
            "derived_interpretations must be a list of objects with interpretation and "
            "supporting_drive_item_ids. unanswered_questions must be a list of strings. "
            "Preserve disagreements instead of reconciling them. "
            f"Question: {question}\nEvidence JSON:\n{json.dumps(compact, ensure_ascii=False)}"
        )
        body = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "keep_alive": 0,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.host}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            proposal = json.loads(str(payload.get("response", "")))
        except (TimeoutError, urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"research synthesis unavailable: {type(exc).__name__}") from exc
        if not isinstance(proposal, dict):
            raise ValueError("research synthesizer returned non-object JSON")
        return proposal


def _source_identity(item: Mapping[str, Any]) -> str:
    prov = item["provenance"]
    digest = prov.get("content_sha256")
    return f"sha256:{digest}" if digest else f"drive:{prov['drive_item_id']}"


def _evidence_maps(
    evidence: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    by_id = {str(item["provenance"]["drive_item_id"]): item for item in evidence}
    sources = {
        drive_id: item
        for drive_id, item in by_id.items()
        if item["claim_eligible"]
        and item["fetch_status"] == "ok"
        and item["provenance"]["source_role"] == "source"
    }
    return by_id, sources


def _support_details(
    ids: Sequence[Any],
    sources: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    details: list[dict[str, Any]] = []
    identities: set[str] = set()
    notebooks: set[str] = set()
    seen_ids: set[str] = set()
    for raw in ids:
        drive_id = str(raw)
        if drive_id in seen_ids or drive_id not in sources:
            continue
        seen_ids.add(drive_id)
        item = sources[drive_id]
        prov = item["provenance"]
        details.append(
            {
                "drive_item_id": drive_id,
                "notebook_id": prov["notebook_id"],
                "notebook_title": prov["notebook_title"],
                "title": prov["title"],
                "modified_time": prov["modified_time"],
                "content_sha256": prov.get("content_sha256"),
            }
        )
        identities.add(_source_identity(item))
        notebooks.add(str(prov["notebook_id"]))
    return details, identities, notebooks


def _validate_common_findings(
    proposal: Mapping[str, Any],
    sources: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    rows = proposal.get("common_findings", [])
    if not isinstance(rows, list):
        return accepted, [{"kind": "common_finding", "reason": "invalid_shape"}]

    for row in rows:
        if not isinstance(row, Mapping):
            rejected.append({"kind": "common_finding", "reason": "invalid_shape"})
            continue
        claim = str(row.get("claim", "")).strip()
        ids = row.get("supporting_drive_item_ids", [])
        if not claim or not isinstance(ids, list):
            rejected.append({"kind": "common_finding", "claim": claim, "reason": "invalid_shape"})
            continue
        support, identities, notebooks = _support_details(ids, sources)
        if len(identities) < 2:
            rejected.append(
                {
                    "kind": "common_finding",
                    "claim": claim,
                    "reason": "fewer_than_two_independent_sources",
                    "support": support,
                }
            )
            continue
        if len(notebooks) < 2:
            rejected.append(
                {
                    "kind": "common_finding",
                    "claim": claim,
                    "reason": "not_cross_notebook",
                    "support": support,
                }
            )
            continue
        accepted.append(
            {
                "claim": claim,
                "support": support,
                "independent_source_count": len(identities),
                "notebook_count": len(notebooks),
            }
        )
    return accepted, rejected


def _validate_disagreements(
    proposal: Mapping[str, Any],
    sources: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    rows = proposal.get("disagreements", [])
    if not isinstance(rows, list):
        return accepted, [{"kind": "disagreement", "reason": "invalid_shape"}]

    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("positions"), list):
            rejected.append({"kind": "disagreement", "reason": "invalid_shape"})
            continue
        topic = str(row.get("topic", "")).strip()
        positions: list[dict[str, Any]] = []
        all_notebooks: set[str] = set()
        all_identities: set[str] = set()
        for pos in row["positions"]:
            if not isinstance(pos, Mapping):
                continue
            claim = str(pos.get("claim", "")).strip()
            ids = pos.get("supporting_drive_item_ids", [])
            if not claim or not isinstance(ids, list):
                continue
            support, identities, notebooks = _support_details(ids, sources)
            if not support:
                continue
            positions.append({"claim": claim, "support": support})
            all_notebooks.update(notebooks)
            all_identities.update(identities)

        if len(positions) < 2 or len(all_identities) < 2:
            rejected.append(
                {
                    "kind": "disagreement",
                    "topic": topic,
                    "reason": "insufficient_supported_positions",
                    "positions": positions,
                }
            )
            continue
        if len(all_notebooks) < 2:
            rejected.append(
                {
                    "kind": "disagreement",
                    "topic": topic,
                    "reason": "not_cross_notebook",
                    "positions": positions,
                }
            )
            continue
        accepted.append(
            {
                "topic": topic,
                "positions": positions,
                "independent_source_count": len(all_identities),
                "notebook_count": len(all_notebooks),
            }
        )
    return accepted, rejected


def _validate_derived(
    proposal: Mapping[str, Any],
    by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    rows = proposal.get("derived_interpretations", [])
    if not isinstance(rows, list):
        return accepted, [{"kind": "derived_interpretation", "reason": "invalid_shape"}]

    for row in rows:
        if not isinstance(row, Mapping):
            rejected.append({"kind": "derived_interpretation", "reason": "invalid_shape"})
            continue
        text = str(row.get("interpretation", "")).strip()
        ids = row.get("supporting_drive_item_ids", [])
        if not text or not isinstance(ids, list):
            rejected.append({"kind": "derived_interpretation", "reason": "invalid_shape"})
            continue

        support = []
        invalid_role = False
        for raw in ids:
            item = by_id.get(str(raw))
            if item is None:
                continue
            role = str(item["provenance"]["source_role"])
            if role == "source" or item["claim_eligible"]:
                invalid_role = True
                continue
            if role in {"derived", "derived-note"} and item["fetch_status"] == "ok":
                prov = item["provenance"]
                support.append(
                    {
                        "drive_item_id": prov["drive_item_id"],
                        "notebook_id": prov["notebook_id"],
                        "notebook_title": prov["notebook_title"],
                        "title": prov["title"],
                        "source_role": role,
                    }
                )
        if invalid_role or not support:
            rejected.append(
                {
                    "kind": "derived_interpretation",
                    "interpretation": text,
                    "reason": "not_purely_derived_context",
                    "support": support,
                }
            )
            continue
        accepted.append({"interpretation": text, "support": support, "claim_eligible": False})
    return accepted, rejected


def research_notebooks(
    catalog: Mapping[str, Any],
    question: str,
    provider: SelectiveTextProvider,
    synthesizer: ResearchSynthesizer,
    *,
    top_k: int = 20,
    max_files: int = 8,
    max_bytes_per_file: int = 65_536,
    max_total_bytes: int = 524_288,
    excerpt_chars: int = 4_000,
    text_hits: Sequence[Mapping[str, Any]] | None = None,
    scope: str = "archive",
) -> dict[str, Any]:
    """Synthesize cross-notebook findings and enforce evidence authority."""

    bundle = retrieve_evidence(
        catalog,
        question,
        provider,
        top_k=top_k,
        max_files=max_files,
        max_bytes_per_file=max_bytes_per_file,
        max_total_bytes=max_total_bytes,
        excerpt_chars=excerpt_chars,
        text_hits=text_hits,
        scope=scope,
    )
    if bundle["status"] == "DELEGATE_RUNTIME":
        return {
            "question": question,
            "status": "DELEGATE_RUNTIME",
            "reason": bundle["reason"],
            "common_findings": [],
            "disagreements": [],
            "source_evidence": [],
            "derived_interpretations": [],
            "unanswered_questions": [],
            "insufficient_support": [],
            "retrieval": bundle,
        }
    if bundle["status"] != "EVIDENCE_READY":
        return {
            "question": question,
            "status": bundle["status"],
            "reason": bundle.get("reason"),
            "common_findings": [],
            "disagreements": [],
            "source_evidence": [
                item for item in bundle["evidence"] if item["claim_eligible"]
            ],
            "derived_interpretations": [],
            "unanswered_questions": [question],
            "insufficient_support": [],
            "retrieval": bundle,
        }

    proposal = synthesizer.synthesize(question, bundle["evidence"])
    by_id, sources = _evidence_maps(bundle["evidence"])
    common, common_rejected = _validate_common_findings(proposal, sources)
    disagreements, disagreement_rejected = _validate_disagreements(proposal, sources)
    derived, derived_rejected = _validate_derived(proposal, by_id)

    unanswered = proposal.get("unanswered_questions", [])
    if not isinstance(unanswered, list):
        unanswered = []
    unanswered_questions = [
        str(value).strip() for value in unanswered if str(value).strip()
    ]

    source_evidence = [
        {
            "excerpt": item["excerpt"],
            "provenance": item["provenance"],
        }
        for item in sources.values()
    ]
    insufficient = [*common_rejected, *disagreement_rejected, *derived_rejected]

    if common or disagreements:
        status = "RESEARCH_READY"
        reason = None
    elif sources:
        status = "INSUFFICIENT_CROSS_SOURCE_EVIDENCE"
        reason = "no synthesis survived independent cross-notebook source validation"
    else:
        status = "MISSING_SOURCE"
        reason = "no claim-eligible source evidence"

    return {
        "question": question,
        "status": status,
        "reason": reason,
        "common_findings": common,
        "disagreements": disagreements,
        "source_evidence": source_evidence,
        "derived_interpretations": derived,
        "unanswered_questions": unanswered_questions,
        "insufficient_support": insufficient,
        "retrieval": bundle,
        "trace": {
            "claim_eligible_sources": len(sources),
            "source_notebooks": len(
                {str(item["provenance"]["notebook_id"]) for item in sources.values()}
            ),
            "accepted_common_findings": len(common),
            "accepted_disagreements": len(disagreements),
            "accepted_derived_interpretations": len(derived),
            "rejected_synthesis_items": len(insufficient),
        },
    }


def write_review_candidate(report: Mapping[str, Any], path: Path) -> Path:
    """Save a local review candidate; never write durable MQ memory."""

    payload = {
        "kind": "notebook-cross-research-review-candidate",
        "status": "candidate",
        "question": report.get("question"),
        "research_status": report.get("status"),
        "common_findings": report.get("common_findings", []),
        "disagreements": report.get("disagreements", []),
        "source_evidence": report.get("source_evidence", []),
        "derived_interpretations": report.get("derived_interpretations", []),
        "unanswered_questions": report.get("unanswered_questions", []),
        "note": "local review candidate only; no automatic durable-memory promotion",
    }
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path
