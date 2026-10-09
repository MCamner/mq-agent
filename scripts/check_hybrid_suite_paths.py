#!/usr/bin/env python3
"""Print the paths a hybrid challenge suite will actually use, and check they exist.

Every path in `mq.hybrid-retrieval-suite.v1` is resolved relative to the
*suite file's own directory*, not the working directory. A suite copied
somewhere else keeps working, silently, against the wrong inputs: the Notebook
channels report unavailable and the run reports NO_MEASURED_GAIN. That reads as
negative evidence about a channel when it is really a misplaced file, which is
worse than a hard failure because it looks like a measurement.

Found exactly that way: moving a suite to /tmp turned three DISCRIMINATING
channels into NO_MEASURED_GAIN, because `../notebook-corpus/catalog.json`
resolved outside the repository.

How a missing path behaves differs by role, and that is the thing worth seeing
before trusting a result:

    fixture          LOUD   the tool raises "fixture file does not exist"
    catalog          QUIET  notebook-keyword reports unavailable
    semantic_index   QUIET  notebook-vector reports unavailable
    codegraph_root   QUIET  codegraph reports unavailable; the directory must
                            contain .codegraph/ or the index is not found

Resolution is not reimplemented here. `_resolve` is imported from the module
that the run itself uses, so this script cannot drift from the behaviour it
reports on. Run under `uv run python` so that import is available.

Exit codes:
    0  every resolved path exists
    1  one or more resolved paths are missing
    2  the suite is missing, unreadable, or violates its contract

Usage:
    uv run python scripts/check_hybrid_suite_paths.py .mq/hybrid-challenge/suite.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from mq_agent.memory.hybrid_evidence import _resolve
from mq_agent.tools.contract_validation import validate_contract

EXIT_OK = 0
EXIT_MISSING = 1
EXIT_INPUT = 2

QUIET = "QUIET  channel reports unavailable"
LOUD = "LOUD   the run raises"


def _row(role: str, raw: object, resolved: Path | None, ok: bool, severity: str) -> None:
    mark = "ok " if ok else "MISS"
    print(f"  {mark}  {role:16} {raw!s:34} -> {resolved}")
    if not ok:
        print(f"        if missing: {severity}")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return EXIT_INPUT

    suite_path = Path(argv[1]).expanduser()
    if not suite_path.is_file():
        print(f"INPUT: suite is missing at {suite_path}", file=sys.stderr)
        return EXIT_INPUT
    try:
        suite = json.loads(suite_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INPUT: suite at {suite_path} is unreadable: {exc}", file=sys.stderr)
        return EXIT_INPUT
    if not isinstance(suite, dict):
        print(f"INPUT: suite at {suite_path} is not a JSON object", file=sys.stderr)
        return EXIT_INPUT
    try:
        validate_contract("hybrid_retrieval_suite.schema.json", suite)
    except Exception as exc:  # contract violation is an input problem, not a miss
        print(f"INPUT: suite does not satisfy its contract: {exc}", file=sys.stderr)
        return EXIT_INPUT

    # The run does suite_path.expanduser().resolve() and takes .parent.
    base = suite_path.resolve().parent
    print(f"suite:  {suite_path.resolve()}")
    print(f"base:   {base}")
    print()

    missing = 0

    shared = {
        "catalog": (suite.get("catalog"), QUIET),
        "semantic_index": (suite.get("semantic_index"), QUIET),
        "codegraph_root": (suite.get("codegraph_root"), QUIET),
    }
    print("suite-level:")
    for role, (raw, severity) in shared.items():
        if raw is None:
            print(f"  --    {role:16} {'(not set)':34} -> inherited default or disabled")
            continue
        resolved = _resolve(base, str(raw))
        if role == "codegraph_root":
            ok = bool(resolved and resolved.is_dir() and (resolved / ".codegraph").is_dir())
        else:
            ok = bool(resolved and resolved.is_file())
        _row(role, raw, resolved, ok, severity)
        missing += 0 if ok else 1
    print()

    print("cases:")
    for case in suite["cases"]:
        print(f"  [{case['id']}] target={case.get('challenge_target') or '(none)'}")
        fixture = _resolve(base, str(case["fixture"]))
        ok = bool(fixture and fixture.is_file())
        _row("fixture", case["fixture"], fixture, ok, LOUD)
        missing += 0 if ok else 1
        for role in ("catalog", "semantic_index", "codegraph_root"):
            raw = case.get(role)
            if raw is None:
                continue
            resolved = _resolve(base, str(raw))
            if role == "codegraph_root":
                ok = bool(
                    resolved and resolved.is_dir() and (resolved / ".codegraph").is_dir()
                )
            else:
                ok = bool(resolved and resolved.is_file())
            _row(f"{role} (case)", raw, resolved, ok, QUIET)
            missing += 0 if ok else 1
    print()

    if missing:
        print(f"PREFLIGHT: FAIL -- {missing} path(s) missing")
        print("           A QUIET miss does not stop the run. It makes the affected")
        print("           channel unavailable, which the result reports as no measured")
        print("           gain rather than as a broken input.")
        return EXIT_MISSING

    print("PREFLIGHT: OK -- every resolved path exists")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
