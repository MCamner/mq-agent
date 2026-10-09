#!/usr/bin/env python3
"""Minimum viability gate: is MQ material represented in the semantic index?

A successful `notebook build --semantic` is not evidence that the index is
usable. The selection is notebook-balanced round-robin over a bounded file
budget, with no topic awareness, so a build can succeed and still produce a
sample containing none of the corpus's MQ-domain material. That is the state
the first index was in: 120 chunks over 22 documents, none MQ-related, while
the catalog held 606 MQ documents out of 6792. A `notebook-vector` challenge
case cannot be honestly discriminating against such an index, because the
relevant material is not reachable at any top_k.

This gate answers one question:

    Is MQ material represented at all?

It deliberately does NOT answer:

    Is the MQ material representative enough for a vector challenge?

So the threshold is >= 1 document, not a percentage. Inventing a coverage
percentage before seeing a real rebuild would be a number with no evidence
behind it. Once a rebuild exists, a second diagnostic level (present / weak /
adequate) can be derived from what the data actually looks like.

Operator gate, not a CI check. The semantic index and the catalog live under
.mq/notebook-corpus/, which is gitignored, so CI has nothing to run this
against. It is deliberately not wired into release-check.sh: that gate must
pass on a clean checkout, and scripts/check-gate-parity.py would then require
a workflow counterpart that cannot exist.

Exit codes:
    0  PASS  -- schema recognised, inputs readable, >= 1 MQ document indexed
    1  FAIL  -- inputs readable but zero MQ documents indexed
    2  INPUT -- missing or unreadable input, unexpected schema, or no chunks

Usage:
    scripts/check_notebook_semantic_mq_coverage.py
    scripts/check_notebook_semantic_mq_coverage.py <index.json> <catalog.json>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

EXPECTED_SCHEMA = "notebook-semantic-index-experiment.v1"

DEFAULT_INDEX = Path(".mq/notebook-corpus/semantic-index.json")
DEFAULT_CATALOG = Path(".mq/notebook-corpus/catalog.json")

# Title-level signal for the MQ domain. Deliberately broad: the question is
# whether anything from this stack's subject matter is present, not how much.
MQ_TITLE = re.compile(
    r"mq[-_ ]|mcp|codegraph|obsidian|repo-signal|igel|ums\b|citrix|hybrid retrieval",
    re.I,
)

EXIT_PASS = 0
EXIT_COVERAGE_FAIL = 1
EXIT_INPUT = 2


def _load(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        print(f"INPUT: {label} is missing at {path}", file=sys.stderr)
        raise SystemExit(EXIT_INPUT)
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INPUT: {label} at {path} is unreadable: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_INPUT) from exc
    if not isinstance(payload, dict):
        print(f"INPUT: {label} at {path} is not a JSON object", file=sys.stderr)
        raise SystemExit(EXIT_INPUT)
    return payload


def _catalog_titles(catalog: dict[str, Any]) -> set[str]:
    items = catalog.get("items")
    if not isinstance(items, list):
        print("INPUT: catalog has no 'items' array", file=sys.stderr)
        raise SystemExit(EXIT_INPUT)
    return {str(row.get("title", "")) for row in items if isinstance(row, dict)}


def main(argv: list[str]) -> int:
    index_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_INDEX
    catalog_path = Path(argv[2]) if len(argv) > 2 else DEFAULT_CATALOG

    index = _load(index_path, "semantic index")
    catalog = _load(catalog_path, "catalog")

    schema = str(index.get("schema", ""))
    if schema != EXPECTED_SCHEMA:
        print(
            f"INPUT: semantic index schema is {schema!r}, expected {EXPECTED_SCHEMA!r}",
            file=sys.stderr,
        )
        return EXIT_INPUT

    chunks = index.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        print("INPUT: semantic index has no usable chunks", file=sys.stderr)
        return EXIT_INPUT

    indexed_titles = {
        str(chunk.get("title", "")) for chunk in chunks if isinstance(chunk, dict)
    }
    indexed_titles.discard("")
    indexed_docs = {
        chunk.get("drive_item_id")
        for chunk in chunks
        if isinstance(chunk, dict) and chunk.get("drive_item_id")
    }
    mq_indexed = sorted(t for t in indexed_titles if MQ_TITLE.search(t))

    catalog_titles = _catalog_titles(catalog)
    catalog_titles.discard("")
    mq_catalog = sum(1 for t in catalog_titles if MQ_TITLE.search(t))

    trace = index.get("trace") or {}

    print(f"index:                      {index_path}")
    print(f"catalog:                    {catalog_path}")
    print(f"schema:                     {schema}")
    print(f"canonical:                  {str(index.get('canonical')).lower()}")
    print(f"disposable:                 {str(index.get('disposable')).lower()}")
    print()
    for key in (
        "files_text_capable",
        "files_selected",
        "notebooks_available",
        "notebooks_selected",
        "files_fetched",
        "files_unavailable",
    ):
        if key in trace:
            print(f"{key + ':':28}{trace[key]}")
    print(f"{'chunks:':28}{len(chunks)}")
    print()
    print(f"MQ docs in catalog:         {mq_catalog} / {len(catalog_titles)}")
    print(f"MQ docs in semantic index:  {len(mq_indexed)} / {len(indexed_docs)}")
    print()

    if not mq_indexed:
        # Part of the gate's report, not an error channel: keeping it on stdout
        # keeps the output in reading order. stderr stays for INPUT problems.
        print("GATE: FAIL")
        print("      The index contains no MQ-domain material, so a notebook-vector")
        print("      challenge cannot be honestly discriminating against it, whatever")
        print("      case or top_k is chosen.")
        return EXIT_COVERAGE_FAIL

    print("MQ titles in the index:")
    for title in mq_indexed[:20]:
        print(f"    {title[:72]}")
    if len(mq_indexed) > 20:
        print(f"    ... {len(mq_indexed) - 20} more")
    print()
    print("GATE: PASS")
    print("      Minimum viability only: MQ material is represented. This does not")
    print("      assert the coverage is representative enough for a vector challenge.")
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main(sys.argv))
