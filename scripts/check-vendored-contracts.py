#!/usr/bin/env python3
"""Prove every vendored contract still matches the canonical one in mqobsidian.

mqobsidian owns these contracts. An installed mq-agent has no vault checkout, so
it ships its own copy inside the wheel and this gate proves the copy has not
drifted:

    canonical in mqobsidian -> vendored here -> this gate -> runtime uses the wheel

What it guarantees is one-directional, and deliberately so: **mq-agent cannot
merge or package a vendored contract that differs from canonical.** It is not a
two-repo transaction. A contract change lands in mqobsidian first; this repo
goes red until its copy catches up. That is the intended sequence, and it is why
the blocking gate lives here, on the consumer, rather than in both repos — a
mirrored blocking gate would deadlock, each repo comparing against the other's
unmerged branch.

Nothing is normalized away. `$id` and `title` are contract content: if canonical
carries one, the vendored copy carries the same one. Only formatting is
ignored, because both files are parsed before comparison.

Adding a contract is one entry in `schemas/vendored-contracts.json`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "schemas" / "vendored-contracts.json"


def differences(canonical: Any, vendored: Any, path: str = "") -> list[str]:
    """Every place the two documents disagree, as dotted paths."""
    where = path or "<root>"
    if type(canonical) is not type(vendored):
        return [f"{where}: canonical is {type(canonical).__name__}, vendored is {type(vendored).__name__}"]

    if isinstance(canonical, dict):
        found: list[str] = []
        for key in sorted(set(canonical) | set(vendored)):
            child = f"{path}.{key}" if path else key
            if key not in vendored:
                found.append(f"{child}: missing from vendored copy")
            elif key not in canonical:
                found.append(f"{child}: present in vendored copy, absent from canonical")
            else:
                found.extend(differences(canonical[key], vendored[key], child))
        return found

    if isinstance(canonical, list):
        if len(canonical) != len(vendored):
            return [f"{where}: canonical has {len(canonical)} items, vendored has {len(vendored)}"]
        return [
            item
            for index, (left, right) in enumerate(zip(canonical, vendored))
            for item in differences(left, right, f"{path}[{index}]")
        ]

    if canonical != vendored:
        return [f"{where}: canonical {canonical!r} != vendored {vendored!r}"]
    return []


def load(path: Path, label: str) -> tuple[Any, str | None]:
    if not path.is_file():
        return None, f"{label} not found: {path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, f"{label} is not valid JSON: {path}: {exc}"


def check(canonical_root: Path, manifest_path: Path = MANIFEST) -> tuple[int, list[str]]:
    report: list[str] = []
    manifest, error = load(manifest_path, "manifest")
    if error:
        return 1, [error]

    contracts = manifest.get("contracts") or []
    if not contracts:
        # A gate that checks nothing passes vacuously, which is worse than no gate.
        return 1, [f"{manifest_path.name} declares no contracts; the gate would pass vacuously"]

    if not canonical_root.is_dir():
        return 1, [
            f"canonical checkout not found: {canonical_root}",
            "Pass --canonical-root <path to an mqobsidian checkout>.",
        ]

    failures = 0
    for entry in contracts:
        name = entry["contract"]
        canonical_path = canonical_root / entry["canonical"]
        vendored_path = ROOT / entry["vendored"]

        canonical, canonical_error = load(canonical_path, f"{name} canonical")
        vendored, vendored_error = load(vendored_path, f"{name} vendored")
        if canonical_error or vendored_error:
            failures += 1
            report.extend(message for message in (canonical_error, vendored_error) if message)
            continue

        drift = differences(canonical, vendored)
        if not drift:
            report.append(f"[ok]    {name}: vendored copy matches canonical")
            continue

        failures += 1
        report.append(f"[DRIFT] {name}")
        report.append(f"          canonical: {canonical_path}")
        report.append(f"          vendored:  {entry['vendored']}  <- behind; update this file")
        report.extend(f"          - {item}" for item in drift[:20])
        if len(drift) > 20:
            report.append(f"          ... and {len(drift) - 20} more")

    if failures:
        report.append("")
        report.append(
            f"{failures} vendored contract(s) differ from canonical. "
            "Canonical lands in mqobsidian first; copy it here to go green."
        )
    return (1 if failures else 0), report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--canonical-root",
        type=Path,
        required=True,
        help="Path to an mqobsidian checkout holding the canonical contracts.",
    )
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args(argv)

    status, report = check(args.canonical_root.expanduser(), args.manifest)
    for line in report:
        print(line)
    return status


if __name__ == "__main__":
    sys.exit(main())
