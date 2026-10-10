"""Contract tests for the candidate source-diversity rule.

The rule was written down before the query it disqualifies was replaced, so the
reason on record is the pool's shape and not the result it produced. At the
time these tests were written no fixture had been labelled, so no case could
have been selected for the answer it gives.

What it caught: a keyword-targeted query returned eight `IGEL_UMS_Web_App_Guide
- Slide N.png` files plus the deck they came from. Nine of ten candidates were
derivatives of one logical document, which makes "did the channel find the
expected ref" nearly the same question as "did it return anything at all".
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_candidate_source_diversity.py"


def _candidates(
    channel_rows: dict[str, list[tuple[str, str]]],
) -> dict[str, Any]:
    return {
        "schema": "mq.hybrid-retrieval-challenge-candidates.v1",
        "status": "PASS",
        "channels": [
            {
                "channel": name,
                "status": "AVAILABLE" if refs else "UNAVAILABLE",
                "returned": len(refs),
                "candidates": [
                    {"ref": ref, "rank": i + 1, "metadata": {"title": title}}
                    for i, (ref, title) in enumerate(refs)
                ],
            }
            for name, refs in channel_rows.items()
        ],
    }


def _run(tmp_path: Path, payload: dict[str, Any], *args: str) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def _slides() -> list[tuple[str, str]]:
    rows = [(f"notebook:slide{n}", f"IGEL_UMS_Web_App_Guide_-_Slide_{n}.png") for n in range(8)]
    rows.append(("notebook:deck", "IGEL_UMS_Web_App_Guide.pdf"))
    rows.append(("notebook:other", "Avancerad sökning med WQL i IGEL UMS Web App.html"))
    return rows


def test_a_pool_of_derivatives_from_one_deck_fails(tmp_path: Path) -> None:
    """The real occurrence: nine of ten candidates derive from one document."""
    result = _run(tmp_path, _candidates({"notebook-keyword": _slides()}))

    assert result.returncode == 1, result.stdout + result.stderr
    assert "DIVERSITY: FAIL" in result.stdout
    assert "notebook-keyword" in result.stdout


def test_slides_and_their_deck_count_as_one_document(tmp_path: Path) -> None:
    """A slide image is a derivative of the deck, not a second source."""
    result = _run(tmp_path, _candidates({"notebook-keyword": _slides()}))

    # Eight slides + the deck collapse to one; the WQL page is the second.
    assert "notebook-keyword" in result.stdout
    assert "documents=2" in result.stdout


def test_distinct_documents_pass(tmp_path: Path) -> None:
    rows = [
        ("notebook:a", "HOWTO IGEL - IGEL Community Docs.html"),
        ("notebook:b", "IGEL OS Base System - GitHub.html"),
        ("notebook:c", "HDX Multimedia Settings for an IGEL OS Citrix Session.html"),
        ("notebook:d", "Unicon eLux Scout - Citrix Product Documentation.html"),
    ]
    result = _run(tmp_path, _candidates({"notebook-vector": rows}))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "DIVERSITY: OK" in result.stdout


def test_the_minimum_is_inclusive(tmp_path: Path) -> None:
    """Exactly three distinct documents satisfies "at least three"."""
    rows = [
        ("notebook:a", "First Document.html"),
        ("notebook:b", "Second Document.html"),
        ("notebook:c", "Third Document.html"),
    ]
    result = _run(tmp_path, _candidates({"notebook-vector": rows}))

    assert result.returncode == 0, result.stdout + result.stderr


def test_two_distinct_documents_fail(tmp_path: Path) -> None:
    rows = [
        ("notebook:a", "First Document.html"),
        ("notebook:b", "First Document.pdf"),
        ("notebook:c", "Second Document.html"),
    ]
    result = _run(tmp_path, _candidates({"notebook-vector": rows}))

    assert result.returncode == 1
    assert "documents=2" in result.stdout


def test_the_same_title_in_different_formats_is_one_document(tmp_path: Path) -> None:
    """`x.pdf.html` and `x.pdf metadata.json` are renderings of one source."""
    rows = [
        ("notebook:a", "03d-IGEL_UMS_Web_App.pdf.html"),
        ("notebook:b", "03d-IGEL_UMS_Web_App.pdf metadata.json"),
        ("notebook:c", "03d-IGEL_UMS_Web_App.pdf"),
    ]
    result = _run(tmp_path, _candidates({"notebook-keyword": rows}))

    assert "documents=1" in result.stdout
    assert result.returncode == 1


def test_each_codegraph_symbol_is_its_own_document(tmp_path: Path) -> None:
    """Derivation collapses a pool; co-location does not.

    Three functions in one module are three distinct code units. Eight slides
    of a deck are eight renderings of one document -- the corpus marks them
    `derived`. The rule is about the first relationship, so grouping symbols by
    their file would measure "shares a container", which is a different thing.

    Grouping by file was the original implementation and it disqualified
    CodeGraph in four of six measured pools. The unit was changed on that
    argument, with the operator deciding and the timing on record in
    EXCLUSIONS.md: the reasoning was available before the measurement, the
    correction was not made until after.
    """
    rows = [
        ("codegraph:mq_agent/memory/hybrid_evidence.py#_fingerprint", ""),
        ("codegraph:mq_agent/memory/hybrid_evidence.py#_resolve", ""),
        ("codegraph:mq_agent/memory/hybrid_evidence.py#_path", ""),
    ]
    result = _run(tmp_path, _candidates({"codegraph": rows}))

    assert "documents=3" in result.stdout
    assert result.returncode == 0


def test_notebook_derivatives_still_collapse(tmp_path: Path) -> None:
    """The counterpart. Loosening CodeGraph must not loosen the notebook rule."""
    result = _run(tmp_path, _candidates({"notebook-keyword": _slides()}))

    assert "documents=2" in result.stdout
    assert result.returncode == 1


def test_an_unavailable_channel_is_not_judged(tmp_path: Path) -> None:
    """No candidates is not a diversity failure; it is a missing channel."""
    payload = _candidates({"notebook-vector": []})

    result = _run(tmp_path, payload)

    assert result.returncode == 0
    assert "not judged" in result.stdout


def test_the_minimum_is_configurable(tmp_path: Path) -> None:
    rows = [("notebook:a", "One.html"), ("notebook:b", "Two.html")]

    assert _run(tmp_path, _candidates({"notebook-vector": rows})).returncode == 1
    assert _run(tmp_path, _candidates({"notebook-vector": rows}), "--min", "2").returncode == 0


def test_a_missing_file_is_an_input_error(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "nope.json")],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert result.returncode == 2
    assert "INPUT:" in result.stderr


def test_a_wrong_schema_is_an_input_error(tmp_path: Path) -> None:
    payload = _candidates({"notebook-vector": [("notebook:a", "One.html")]})
    payload["schema"] = "mq.something-else.v1"

    result = _run(tmp_path, payload)

    assert result.returncode == 2
    assert "INPUT:" in result.stderr
