"""D7 interaction-history and research-gap analysis.

Interaction history describes prior inquiry. It never proves facts.

This module selectively reads interaction-role files, extracts question-shaped
utterances deterministically, deduplicates them, and compares those questions
with D3/D4 corpus metadata. It does not use embeddings and it does not promote
interaction text into claim-eligible evidence.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, Sequence

from mq_agent.notebook_corpus import validate_catalog
from mq_agent.notebook_corpus_search import query_terms, search_catalog

_QUESTION_WORDS = (
    "what",
    "why",
    "how",
    "when",
    "where",
    "which",
    "who",
    "can",
    "could",
    "should",
    "would",
    "is",
    "are",
    "do",
    "does",
    "did",
    "vad",
    "varför",
    "hur",
    "när",
    "var",
    "vilken",
    "vilka",
    "vem",
    "kan",
    "kunde",
    "bör",
    "ska",
    "är",
    "gör",
)
_SPACE_RE = re.compile(r"\s+")
_PREFIX_RE = re.compile(r"^(user|you|human|question|q)\s*[:>-]\s*", re.I)
_LIST_PREFIX_RE = re.compile(r"^[-*•]\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[?.!])\s+|[\r\n]+")
_PUNCT_RE = re.compile(r"[^0-9A-Za-zÀ-ÖØ-öø-ÿ? ]+")
_MIN_QUESTION_CHARS = 8


class InteractionTextProvider(Protocol):
    def fetch_text(
        self,
        drive_item_id: str,
        mime_type: str,
        *,
        max_bytes: int,
    ) -> Mapping[str, Any]: ...


def _notebook_titles(catalog: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(row["notebook_id"]): str(row["title"])
        for row in catalog["notebooks"]
    }


def _question_candidate(text: str) -> str | None:
    value = _LIST_PREFIX_RE.sub("", text.strip())
    value = _PREFIX_RE.sub("", value).strip()
    if len(value) < _MIN_QUESTION_CHARS:
        return None

    lowered = value.lower()
    starts_question_word = any(
        lowered == word or lowered.startswith(word + " ")
        for word in _QUESTION_WORDS
    )
    if "?" not in value and not starts_question_word:
        return None

    if "?" in value:
        value = value.split("?", 1)[0].strip() + "?"
    return value or None


def normalize_question(question: str) -> str:
    """Return the deterministic question key used for deduplication."""

    value = question.strip().lower()
    value = _PREFIX_RE.sub("", value)
    value = value.replace("?", " ")
    value = _PUNCT_RE.sub(" ", value)
    return _SPACE_RE.sub(" ", value).strip()


def question_fingerprint(question_key: str) -> str:
    return hashlib.sha256(question_key.encode("utf-8")).hexdigest()[:24]


def extract_questions(text: str) -> list[dict[str, str]]:
    """Extract question-shaped statements without semantic inference."""

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for segment in _SENTENCE_SPLIT_RE.split(text):
        question = _question_candidate(segment)
        if question is None:
            continue
        key = normalize_question(question)
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "question": question,
                "question_key": key,
                "question_id": question_fingerprint(key),
            }
        )
    return rows


def collect_questions(
    catalog: Mapping[str, Any],
    provider: InteractionTextProvider,
    *,
    max_files: int = 20,
    max_bytes_per_file: int = 65_536,
    max_total_bytes: int = 524_288,
) -> dict[str, Any]:
    """Read a bounded set of interaction files and deduplicate questions."""

    validate_catalog(catalog)
    if max_files < 1:
        raise ValueError("max_files must be at least 1")
    if max_bytes_per_file < 1 or max_total_bytes < 1:
        raise ValueError("byte limits must be positive")

    notebook_titles = _notebook_titles(catalog)
    interactions = [
        item
        for item in catalog["items"]
        if str(item["classification"]["role"]) == "interaction"
    ]
    interactions.sort(
        key=lambda row: (
            str(row["notebook_id"]),
            str(row["modified_time"]),
            str(row["item_id"]),
        )
    )

    selected = interactions[:max_files]
    total_bytes = 0
    fetched = 0
    unavailable = 0
    occurrences: dict[str, list[dict[str, Any]]] = defaultdict(list)
    display_question: dict[str, str] = {}

    for item in selected:
        remaining = max_total_bytes - total_bytes
        if remaining <= 0:
            break
        limit = min(max_bytes_per_file, remaining)
        response = provider.fetch_text(
            str(item["drive_item_id"]),
            str(item["mime_type"]),
            max_bytes=limit,
        )
        status = str(response.get("status", "unavailable"))
        if status != "ok":
            unavailable += 1
            continue

        text = str(response.get("text", ""))
        bytes_fetched = int(response.get("bytes_fetched", len(text.encode("utf-8"))))
        total_bytes += max(0, bytes_fetched)
        fetched += 1

        for row in extract_questions(text):
            key = row["question_key"]
            display_question.setdefault(key, row["question"])
            occurrences[key].append(
                {
                    "drive_item_id": item["drive_item_id"],
                    "notebook_id": item["notebook_id"],
                    "notebook_title": notebook_titles[str(item["notebook_id"])],
                    "interaction_title": item["title"],
                    "modified_time": item["modified_time"],
                    "source_role": "interaction",
                    "claim_eligible": False,
                }
            )

    questions: list[dict[str, Any]] = []
    for key in sorted(occurrences):
        rows = occurrences[key]
        notebook_ids = sorted({str(row["notebook_id"]) for row in rows})
        questions.append(
            {
                "question_id": question_fingerprint(key),
                "question": display_question[key],
                "question_key": key,
                "occurrence_count": len(rows),
                "notebook_count": len(notebook_ids),
                "recurring": len(rows) > 1,
                "cross_notebook": len(notebook_ids) > 1,
                "interaction_trace": rows,
                "evidence_role": "inquiry-history-only",
                "claim_eligible": False,
            }
        )

    questions.sort(
        key=lambda row: (
            -int(row["occurrence_count"]),
            -int(row["notebook_count"]),
            str(row["question_key"]),
        )
    )

    return {
        "status": "QUESTIONS_READY",
        "questions": questions,
        "trace": {
            "interaction_items_available": len(interactions),
            "interaction_items_selected": len(selected),
            "interaction_items_fetched": fetched,
            "interaction_items_unavailable": unavailable,
            "bytes_fetched": total_bytes,
            "unique_questions": len(questions),
            "recurring_questions": sum(1 for row in questions if row["recurring"]),
            "cross_notebook_questions": sum(
                1 for row in questions if row["cross_notebook"]
            ),
        },
    }


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_days(snapshot_at: str, modified_time: str) -> int | None:
    snapshot = _parse_time(snapshot_at)
    modified = _parse_time(modified_time)
    if snapshot is None or modified is None:
        return None
    return max(0, (snapshot - modified).days)


def analyze_gaps(
    catalog: Mapping[str, Any],
    question_report: Mapping[str, Any],
    *,
    text_hits: Sequence[Mapping[str, Any]] | None = None,
    top_k: int = 20,
    stale_after_days: int = 365,
) -> dict[str, Any]:
    """Classify prior questions by available source/derived support."""

    validate_catalog(catalog)
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if stale_after_days < 1:
        raise ValueError("stale_after_days must be positive")

    rows: list[dict[str, Any]] = []
    for question in question_report.get("questions", []):
        text = str(question["question"])
        search = search_catalog(
            catalog,
            text,
            top_k=top_k,
            text_hits=text_hits,
        )
        source_matches = [
            hit for hit in search["results"] if hit["source_role"] == "source"
        ]
        derived_matches = [
            hit
            for hit in search["results"]
            if hit["source_role"] in {"derived", "derived-note"}
        ]

        if source_matches:
            state = "SOURCE_MATCHES_PRESENT"
        elif derived_matches:
            state = "DERIVED_ONLY"
        else:
            state = "NO_SOURCE_EVIDENCE"

        source_ages = [
            age
            for hit in source_matches
            if (age := _age_days(str(catalog["snapshot_at"]), str(hit["modified_time"])))
            is not None
        ]
        stale = bool(source_ages) and all(age >= stale_after_days for age in source_ages)

        rows.append(
            {
                "question_id": question["question_id"],
                "question": text,
                "question_key": question["question_key"],
                "occurrence_count": question["occurrence_count"],
                "notebook_count": question["notebook_count"],
                "recurring": question["recurring"],
                "cross_notebook": question["cross_notebook"],
                "gap_state": "STALE_SOURCE_THEME" if stale else state,
                "source_matches": [
                    {
                        "drive_item_id": hit["drive_item_id"],
                        "notebook_id": hit["notebook_id"],
                        "notebook_title": hit["notebook_title"],
                        "title": hit["title"],
                        "modified_time": hit["modified_time"],
                        "source_role": hit["source_role"],
                    }
                    for hit in source_matches
                ],
                "derived_matches": [
                    {
                        "drive_item_id": hit["drive_item_id"],
                        "notebook_id": hit["notebook_id"],
                        "notebook_title": hit["notebook_title"],
                        "title": hit["title"],
                        "modified_time": hit["modified_time"],
                        "source_role": hit["source_role"],
                    }
                    for hit in derived_matches
                ],
                "interaction_trace": question["interaction_trace"],
                "interaction_is_evidence": False,
                "claim_eligible": False,
                "search_trace": search["trace"],
            }
        )

    priority = {
        "NO_SOURCE_EVIDENCE": 0,
        "DERIVED_ONLY": 1,
        "STALE_SOURCE_THEME": 2,
        "SOURCE_MATCHES_PRESENT": 3,
    }
    rows.sort(
        key=lambda row: (
            priority.get(str(row["gap_state"]), 99),
            -int(row["occurrence_count"]),
            -int(row["notebook_count"]),
            str(row["question_id"]),
        )
    )

    return {
        "status": "GAPS_READY",
        "gaps": rows,
        "summary": {
            "questions": len(rows),
            "no_source_evidence": sum(
                1 for row in rows if row["gap_state"] == "NO_SOURCE_EVIDENCE"
            ),
            "derived_only": sum(
                1 for row in rows if row["gap_state"] == "DERIVED_ONLY"
            ),
            "stale_source_themes": sum(
                1 for row in rows if row["gap_state"] == "STALE_SOURCE_THEME"
            ),
            "source_matches_present": sum(
                1 for row in rows if row["gap_state"] == "SOURCE_MATCHES_PRESENT"
            ),
        },
        "trace": {
            "semantic_embeddings_used": False,
            "interaction_promoted_to_evidence": False,
            "stale_after_days": stale_after_days,
        },
    }
