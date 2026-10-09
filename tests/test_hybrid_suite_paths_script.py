"""Contract tests for the hybrid challenge suite path preflight.

The script exists because suite paths resolve against the suite file's own
directory. A suite in the wrong place keeps running against inputs that are not
there, and the result reads as negative channel evidence rather than as a
broken input. These tests pin the two verdicts that distinction depends on.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_hybrid_suite_paths.py"


def _suite_tree(base: Path, *, catalog_rel: str) -> Path:
    """Write a minimal but contract-valid suite with its fixture beside it."""
    base.mkdir(parents=True, exist_ok=True)
    (base / "fixture.json").write_text(
        json.dumps(
            {
                "schema": "mq.hybrid-retrieval-fixture.v1",
                "expected_refs": ["notebook:abc"],
                "contradicted_refs": [],
                "stale_refs": [],
            }
        ),
        encoding="utf-8",
    )
    suite = {
        "schema": "mq.hybrid-retrieval-suite.v1",
        "catalog": catalog_rel,
        "cases": [
            {
                "id": "case-1",
                "task_class": "docs",
                "query": "anything",
                "fixture": "fixture.json",
                "challenge_target": "notebook-keyword",
            }
        ],
    }
    path = base / "suite.json"
    path.write_text(json.dumps(suite), encoding="utf-8")
    return path


def _run(suite: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(suite)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def test_preflight_passes_when_every_resolved_path_exists(tmp_path: Path) -> None:
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "catalog.json").write_text("{}", encoding="utf-8")
    suite = _suite_tree(tmp_path / "challenge", catalog_rel="../corpus/catalog.json")

    result = _run(suite)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PREFLIGHT: OK" in result.stdout


def test_preflight_fails_when_a_relative_path_resolves_to_nothing(
    tmp_path: Path,
) -> None:
    """The misplaced-suite case, which otherwise runs and reports no gain.

    In the real occurrence the path resolved outside the repository; here it
    resolves inside the temporary tree to a file that was never created. Both
    are the same fact to the run: the input is not where the suite says.
    """
    suite = _suite_tree(tmp_path / "challenge", catalog_rel="../corpus/catalog.json")

    result = _run(suite)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "PREFLIGHT: FAIL" in result.stdout
    # The fixture sits beside the suite and must still be found, so the failure
    # is attributable rather than a blanket "something is wrong".
    assert "MISS  catalog" in result.stdout
    assert "ok   fixture" in result.stdout


def test_missing_suite_is_an_input_error_not_a_path_miss(tmp_path: Path) -> None:
    result = _run(tmp_path / "nope.json")

    assert result.returncode == 2
    assert "INPUT:" in result.stderr


def test_contract_violation_is_an_input_error(tmp_path: Path) -> None:
    suite = tmp_path / "suite.json"
    suite.write_text(
        json.dumps({"schema": "mq.hybrid-retrieval-suite.v1", "cases": [{"id": "x"}]}),
        encoding="utf-8",
    )

    result = _run(suite)

    assert result.returncode == 2
    assert "contract" in result.stderr.lower()
