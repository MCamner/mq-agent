"""P1 must not report PASS for an index it failed to populate.

Driving the real build surfaced this. With an expired Drive token every one of
356 fetches came back `http_401`, and the stage reported:

    {"stage": "P1", "status": "PASS", "chunks": 0, "files_fetched": 0}

It then wrote that 834-byte index over the previous one. Two faults in one
result: a declared PASS that is evidence of nothing, and the loss of the only
index on disk.

The split matters. `build_semantic_index` stays a pure builder that always
returns a traceable result -- the trace of a total starvation is exactly what
the budget-loss diagnosis inspects -- while `build_semantic_stage` is the thing
that writes the file and declares PASS, so the refusal belongs there. Refusing
before the write is what keeps the previous index.

Scope is deliberately narrow: every attempt failed. A partial fetch is not
judged here, because "is this index good enough" is a different question with a
different answer, and `check_notebook_semantic_mq_coverage.py` already asks it.
Widening this to a ratio would smuggle a quality threshold into a liveness
check.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from mq_agent.notebook_corpus import build_from_document
from mq_agent.notebook_pipeline import build_semantic_stage


def _catalog() -> Mapping[str, Any]:
    doc = {
        "corpus_key": "notebooklm-archive",
        "snapshot_at": "2026-09-29T00:00:00Z",
        "notebooks": [
            {"drive_item_id": "nb-a", "title": "Notebook A"},
            {"drive_item_id": "nb-b", "title": "Notebook B"},
        ],
        "items": [
            {
                "drive_item_id": f"src-{n}",
                "notebook_drive_item_id": f"nb-{'a' if n < 2 else 'b'}",
                "parent_drive_item_id": f"s{n}",
                "relative_path": f"Sources/doc{n}.md",
                "title": f"document {n}",
                "mime_type": "text/markdown",
                "size_bytes": 100,
                "modified_time": "2026-09-20T00:00:00Z",
                "origin_provider": "google-drive",
                "content_sha256": chr(ord("a") + n) * 64,
            }
            for n in range(4)
        ],
    }
    return build_from_document(doc)[0]


class RejectingProvider:
    """Every fetch is refused, as an expired OAuth token refuses every fetch."""

    def __init__(self, reason: str = "http_401") -> None:
        self.reason = reason

    def fetch_text(
        self, drive_item_id: str, mime_type: str, *, max_bytes: int
    ) -> Mapping[str, Any]:
        return {"status": "unavailable", "reason": self.reason, "text": ""}


class PartialProvider:
    """Serves one document and refuses the rest."""

    def __init__(self, served: str) -> None:
        self.served = served

    def fetch_text(
        self, drive_item_id: str, mime_type: str, *, max_bytes: int
    ) -> Mapping[str, Any]:
        if drive_item_id != self.served:
            return {"status": "unavailable", "reason": "http_401", "text": ""}
        text = "MQ stack notes about IGEL OS and UMS."
        return {"status": "ok", "text": text, "bytes_fetched": len(text)}


class ServingProvider:
    def fetch_text(
        self, drive_item_id: str, mime_type: str, *, max_bytes: int
    ) -> Mapping[str, Any]:
        text = f"text for {drive_item_id} about MQ and IGEL"
        return {"status": "ok", "text": text, "bytes_fetched": len(text)}


class FixedEmbedding:
    def embed(self, texts: Any) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def test_every_fetch_refused_is_not_a_pass(tmp_path: Path) -> None:
    """The defect. 356 of 356 refused, reported as PASS."""
    with pytest.raises(RuntimeError) as exc:
        build_semantic_stage(
            _catalog(),
            RejectingProvider(),
            FixedEmbedding(),
            output_path=tmp_path / "semantic-index.json",
        )

    assert "http_401" in str(exc.value)


def test_the_refusal_names_the_dominant_reason(tmp_path: Path) -> None:
    """`http_401` and "no readable text" call for opposite actions.

    One means the credential is wrong; the other means the corpus holds no text
    at this budget. Reporting the count without the reason sends the operator
    to raise a budget that was never the problem.
    """
    with pytest.raises(RuntimeError, match="no_readable_text_in_budget"):
        build_semantic_stage(
            _catalog(),
            RejectingProvider(reason="no_readable_text_in_budget"),
            FixedEmbedding(),
            output_path=tmp_path / "semantic-index.json",
        )


def test_a_failed_build_leaves_the_previous_index_in_place(tmp_path: Path) -> None:
    """Refusing before the write is the point.

    The real occurrence replaced a 120-chunk index with 834 empty bytes. The
    index is `disposable: true`, so this is not a data-integrity rule -- it is
    that a rebuild which fetched nothing has no business destroying the only
    thing available to measure against.
    """
    output = tmp_path / "semantic-index.json"
    previous = {"schema": "notebook-semantic-index-experiment.v1", "chunks": [1, 2, 3]}
    output.write_text(json.dumps(previous), encoding="utf-8")

    with pytest.raises(RuntimeError):
        build_semantic_stage(
            _catalog(), RejectingProvider(), FixedEmbedding(), output_path=output
        )

    assert json.loads(output.read_text()) == previous


def test_a_partial_fetch_still_passes(tmp_path: Path) -> None:
    """Liveness, not quality. Whether one document is enough is the gate's call."""
    report = build_semantic_stage(
        _catalog(),
        PartialProvider(served="src-0"),
        FixedEmbedding(),
        output_path=tmp_path / "semantic-index.json",
    )

    assert report["status"] == "PASS"
    assert report["files_fetched"] == 1
    assert report["chunks"] >= 1


def test_a_catalog_with_nothing_to_attempt_is_not_a_failure(tmp_path: Path) -> None:
    """Nothing was attempted, so nothing was refused.

    The rule is about fetches that failed, not about an index being small. A
    catalog holding no text-capable item produces an empty index without any
    fetch having gone wrong, and must not be reported as a broken credential.
    """
    catalog = dict(_catalog())
    catalog["items"] = [
        {**row, "mime_type": "image/png"} for row in catalog["items"]
    ]

    report = build_semantic_stage(
        catalog,
        RejectingProvider(),
        FixedEmbedding(),
        output_path=tmp_path / "semantic-index.json",
    )

    assert report["status"] == "PASS"
    assert report["files_fetched"] == 0
    assert (tmp_path / "semantic-index.json").is_file()


def test_a_healthy_build_still_writes_and_passes(tmp_path: Path) -> None:
    output = tmp_path / "semantic-index.json"

    report = build_semantic_stage(
        _catalog(), ServingProvider(), FixedEmbedding(), output_path=output
    )

    assert report["status"] == "PASS"
    assert report["files_fetched"] == 4
    assert report["embedding_dimension"] == 2
    assert len(json.loads(output.read_text())["chunks"]) == report["chunks"]
