#!/usr/bin/env python3
"""Does a candidate pool contain enough distinct source documents to measure?

THE RULE
--------
A challenge case must not be used when its candidate pool is dominated by
derivatives of the same logical source document -- several PNG slides from one
deck, say. A valid case has at least three distinct logical source documents
among its candidates.

This is written down as a gate rather than as prose so the reason a case was
disqualified is the shape of its pool, checkable afterwards, and not the result
it happened to produce. It was committed before any fixture had been labelled,
so at the time no case could have been chosen for the answer it gives.

WHAT IT CAUGHT
--------------
A keyword-targeted query returned eight `IGEL_UMS_Web_App_Guide - Slide N.png`
files plus the deck they came from: nine of ten candidates derived from one
logical document. In such a pool "did the channel retrieve the expected ref"
collapses into "did it return anything at all", and a recall of 1.0 says
nothing about ranking.

WHAT A LOGICAL SOURCE DOCUMENT IS
---------------------------------
    notebook:  the title with format and derivative suffixes removed, so
               `x.pdf`, `x.pdf.html`, `x.pdf metadata.json` and
               `x - Slide 4.png` are one document
    codegraph: the whole `path#symbol` ref, since each symbol is its own unit
    anything else: the ref itself

The distinction is derivation, not co-location. Three functions in one module
are three distinct code units; eight slides of a deck are eight renderings of
one document, which the corpus itself marks `derived`. Grouping CodeGraph refs
by their file would measure "shares a container" instead, which is a different
property.

That file-level grouping was the first implementation, and it disqualified
CodeGraph in four of six measured pools. The unit was changed on the argument
above, by operator decision, and the sequence is recorded in
.mq/hybrid-challenge/EXCLUSIONS.md -- the reasoning held before the
measurement, the correction came after it. Read that note before changing the
unit again.

A channel with no candidates is not judged: that is an unavailable channel, a
different fact with a different remedy.

Operator gate, not a CI check. Candidate pools live under .mq/hybrid-challenge/,
which is gitignored, so CI has nothing to run this against. It is deliberately
not wired into release-check.sh: that gate must pass on a clean checkout, and
scripts/check-gate-parity.py would then demand a workflow counterpart that
cannot exist.

Exit codes:
    0  every available channel has at least the minimum
    1  at least one available channel is below it
    2  the file is missing, unreadable, or not a candidates document

Usage:
    scripts/check_candidate_source_diversity.py <candidates.json> [--min 3]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

EXPECTED_SCHEMA = "mq.hybrid-retrieval-challenge-candidates.v1"

EXIT_OK = 0
EXIT_BELOW_MINIMUM = 1
EXIT_INPUT = 2

# Stripped in order: a trailing derivative marker, then any chain of format
# extensions, so `Guide_-_Slide_4.png` and `Guide.pdf.html` reach `guide`.
_DERIVATIVE = re.compile(r"[\s_-]*-[\s_-]*slide[\s_-]*\d+\s*$|\s+metadata\s*$", re.I)
_EXTENSION = re.compile(r"\.(html?|pdf|png|jpe?g|md|json|txt|csv|docx?|pptx?)\s*$", re.I)


def _logical_document(ref: str, title: str) -> str:
    if ref.startswith("codegraph:"):
        return ref
    if not ref.startswith("notebook:"):
        return ref
    name = (title or ref).strip()
    while True:
        stripped = _EXTENSION.sub("", _DERIVATIVE.sub("", name)).strip()
        if stripped == name:
            return stripped.lower() or ref
        name = stripped


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=True, description=__doc__)
    parser.add_argument("candidates")
    parser.add_argument("--min", type=int, default=3, dest="minimum")
    args = parser.parse_args(argv[1:])

    path = Path(args.candidates).expanduser()
    if not path.is_file():
        print(f"INPUT: candidates file is missing at {path}", file=sys.stderr)
        return EXIT_INPUT
    try:
        payload: Any = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INPUT: {path} is unreadable: {exc}", file=sys.stderr)
        return EXIT_INPUT
    if not isinstance(payload, dict):
        print(f"INPUT: {path} is not a JSON object", file=sys.stderr)
        return EXIT_INPUT
    schema = str(payload.get("schema", ""))
    if schema != EXPECTED_SCHEMA:
        print(
            f"INPUT: schema is {schema!r}, expected {EXPECTED_SCHEMA!r}",
            file=sys.stderr,
        )
        return EXIT_INPUT
    channels = payload.get("channels")
    if not isinstance(channels, list):
        print("INPUT: candidates file has no 'channels' array", file=sys.stderr)
        return EXIT_INPUT

    print(f"candidates: {path}")
    print(f"minimum:    {args.minimum} distinct logical source documents")
    print()

    below = 0
    for channel in channels:
        if not isinstance(channel, dict):
            continue
        name = str(channel.get("channel", "?"))
        rows = channel.get("candidates") or []
        if not rows:
            print(f"  --    {name:18} no candidates -- not judged (channel unavailable)")
            continue
        groups: dict[str, list[str]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            metadata = row.get("metadata") or {}
            key = _logical_document(
                str(row.get("ref", "")), str(metadata.get("title", ""))
            )
            groups.setdefault(key, []).append(str(row.get("ref", "")))
        ok = len(groups) >= args.minimum
        mark = "ok " if ok else "LOW"
        print(f"  {mark}  {name:18} candidates={len(rows):3} documents={len(groups)}")
        if not ok:
            below += 1
            for key, refs in sorted(groups.items(), key=lambda r: (-len(r[1]), r[0])):
                print(f"          {len(refs):3} x  {key[:60]}")
    print()

    if below:
        print(f"DIVERSITY: FAIL -- {below} channel(s) below the minimum")
        print("           The pool is dominated by derivatives of too few source")
        print("           documents, so retrieving the expected ref is close to")
        print("           retrieving anything. Replace the query, do not relabel.")
        return EXIT_BELOW_MINIMUM

    print("DIVERSITY: OK -- every available channel meets the minimum")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
