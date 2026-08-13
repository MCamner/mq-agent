"""Fresh-resolve tests for the stack compatibility gate.

Phase 4 of `mq.stack-compatibility.v1`: what a *new* installation would select,
as opposed to what a lockfile happens to hold today.

No test here touches the network or the uv binary. Every run goes through an
injected runner, so the classification logic — which is the part that decides
whether an unreachable registry is reported as incompatibility — is tested
deterministically.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from mq_agent.tools.stack_compatibility import build_report

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / "mq_stack_compatibility.schema.json"

# uv reports an unreachable registry and a genuine conflict with the same
# headline. These are verbatim from uv 0.12.3.
CONFLICT_STDERR = (
    "  x No solution found when resolving dependencies:\n"
    "  `-> Because you require mcp>=1.27.1,<2 and mcp>=2, we can conclude that "
    "your requirements are unsatisfiable.\n"
)
OFFLINE_STDERR = (
    "  x No solution found when resolving dependencies:\n"
    "  `-> Because mcp was not found in the cache and you require mcp>=1.27.1,"
    "<2, we can conclude that your requirements are unsatisfiable.\n"
    "\nhint: Packages were unavailable because the network was disabled.\n"
)


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


class FakeRunner:
    """Stand-in for the subprocess runner, recording every invocation."""

    def __init__(
        self,
        compile_result: tuple[int, str, str] = (0, "mcp==1.27.1\n", ""),
        probe_result: tuple[int, str, str] = (0, "", ""),
        raises: BaseException | None = None,
    ) -> None:
        self.compile_result = compile_result
        self.probe_result = probe_result
        self.raises = raises
        self.calls: list[tuple[list[str], Path, int]] = []

    def __call__(
        self, argv: list[str], cwd: Path, timeout: int
    ) -> tuple[int, str, str]:
        self.calls.append((list(argv), cwd, timeout))
        if self.raises is not None:
            raise self.raises
        return self.compile_result if "compile" in argv else self.probe_result

    @property
    def compiles(self) -> list[list[str]]:
        return [argv for argv, _, _ in self.calls if "compile" in argv]

    @property
    def probes(self) -> list[list[str]]:
        return [argv for argv, _, _ in self.calls if "compile" not in argv]


def _make_repo(
    root: Path,
    name: str,
    *,
    declared: str | None = "mcp>=1.27.1,<2",
    locked: str | None = "1.27.1",
    compat: dict[str, Any] | None = None,
    requires_python: str | None = None,
) -> dict[str, str]:
    repo = root / name
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "VERSION").write_text("1.0.0\n", encoding="utf-8")

    contract: dict[str, Any] = {"repo": name, "role": "test", "version": "1.0.0"}
    if compat is not None:
        contract["compatibility"] = compat
    (repo / ".mq").mkdir(exist_ok=True)
    (repo / ".mq" / "repo-contract.json").write_text(
        json.dumps(contract), encoding="utf-8"
    )

    if declared is not None:
        python = f"requires-python = '{requires_python}'\n" if requires_python else ""
        (repo / "pyproject.toml").write_text(
            "[project]\nname = 'x'\nversion = '1'\n"
            f"{python}dependencies = ['{declared}']\n",
            encoding="utf-8",
        )
    if locked is not None:
        (repo / "uv.lock").write_text(
            f'version = 1\n\n[[package]]\nname = "mcp"\nversion = "{locked}"\n',
            encoding="utf-8",
        )

    return {"name": name, "path": str(repo), "role": "test"}


BOUNDED = {
    "protocols": {"mcp_api": "1.x-fastmcp"},
    "dependencies": {"mcp": ">=1.27.1,<2"},
}
# An unbounded range with no declared protocol track: the static gate can only
# warn about it, so whatever the fresh resolution finds is attributable.
UNBOUNDED = {
    "dependencies": {"mcp": ">=1.27.1"},
    "import_probes": {"mcp": "from mcp.server.fastmcp import FastMCP"},
}


def _fresh(entries: list[dict[str, str]], runner: FakeRunner) -> dict[str, Any]:
    return build_report(
        repos=entries, slice_only=False, fresh_resolve=True, runner=runner, uv_path="uv"
    )


def _codes(report: dict[str, Any]) -> list[str]:
    return [f["code"] for f in report["findings"]]


def _dependency(report: dict[str, Any], repo: str, name: str) -> dict[str, Any]:
    component = next(c for c in report["components"] if c["repo"] == repo)
    return next(d for d in component["dependencies"] if d["name"] == name)


# ── mode and resolved versions ─────────────────────────────────────────────


def test_static_mode_is_the_default_and_runs_nothing(tmp_path) -> None:
    runner = FakeRunner()
    report = build_report(
        repos=[_make_repo(tmp_path, "repo-a", compat=BOUNDED)], slice_only=False
    )
    assert report["mode"] == "static"
    assert _dependency(report, "repo-a", "mcp")["resolved"] is None
    assert runner.calls == []


def test_fresh_resolve_records_what_a_new_install_would_select(tmp_path) -> None:
    runner = FakeRunner(compile_result=(0, "anyio==4.14.2\nmcp==1.27.1\n", ""))
    report = _fresh([_make_repo(tmp_path, "repo-a", compat=BOUNDED)], runner)

    assert report["mode"] == "fresh-resolve"
    assert _dependency(report, "repo-a", "mcp")["resolved"] == "1.27.1"
    assert report["status"] == "PASS"
    assert runner.compiles, "the resolver was never invoked"


def test_fresh_resolve_report_validates_against_schema(tmp_path, validator) -> None:
    report = _fresh([_make_repo(tmp_path, "repo-a", compat=BOUNDED)], FakeRunner())
    errors = list(validator.iter_errors(report))
    assert not errors, [e.message for e in errors]


# ── unavailable is not incompatible ────────────────────────────────────────


def test_network_failure_is_unavailable_not_incompatibility(tmp_path) -> None:
    # uv reports an unreachable registry with the same "No solution found"
    # headline as a real conflict. Reading only that headline would turn every
    # offline CI run into a release-blocking FAIL.
    runner = FakeRunner(compile_result=(1, "", OFFLINE_STDERR))
    report = _fresh([_make_repo(tmp_path, "repo-a", compat=BOUNDED)], runner)

    assert "MQC014_FRESH_RESOLVE_UNAVAILABLE" in _codes(report)
    assert "MQC017_RESOLVE_CONFLICT" not in _codes(report)
    assert report["status"] == "UNAVAILABLE"
    assert all(not f["blocks_release"] for f in report["findings"])


def test_genuine_conflict_is_fail(tmp_path) -> None:
    runner = FakeRunner(compile_result=(1, "", CONFLICT_STDERR))
    report = _fresh([_make_repo(tmp_path, "repo-a", compat=BOUNDED)], runner)

    conflict = next(
        f for f in report["findings"] if f["code"] == "MQC017_RESOLVE_CONFLICT"
    )
    assert conflict["severity"] == "FAIL"
    assert conflict["blocks_release"] is True
    assert report["status"] == "FAIL"


def test_unrecognised_resolver_failure_is_unavailable(tmp_path) -> None:
    runner = FakeRunner(compile_result=(2, "", "error: something new in uv\n"))
    report = _fresh([_make_repo(tmp_path, "repo-a", compat=BOUNDED)], runner)

    assert "MQC014_FRESH_RESOLVE_UNAVAILABLE" in _codes(report)
    assert report["status"] == "UNAVAILABLE"


def test_timeout_is_unavailable(tmp_path) -> None:
    runner = FakeRunner(raises=subprocess.TimeoutExpired(cmd=["uv"], timeout=180))
    report = _fresh([_make_repo(tmp_path, "repo-a", compat=BOUNDED)], runner)

    finding = next(
        f for f in report["findings"] if f["code"] == "MQC014_FRESH_RESOLVE_UNAVAILABLE"
    )
    assert "timed out" in finding["message"]
    assert report["status"] == "UNAVAILABLE"


def test_missing_uv_is_reported_once_as_tool_unavailable(tmp_path) -> None:
    entries = [
        _make_repo(tmp_path, "repo-a", compat=BOUNDED),
        _make_repo(tmp_path, "repo-b", compat=BOUNDED),
    ]
    report = build_report(
        repos=entries, slice_only=False, fresh_resolve=True, uv_path=None
    )

    assert _codes(report).count("MQC010_TOOL_UNAVAILABLE") == 1
    assert report["status"] == "UNAVAILABLE"
    # The missing piece is the tool, not the repository.
    assert report["next_action"] == "Install uv, then re-run with --fresh-resolve"


def test_python_version_mismatch_is_not_a_range_conflict(tmp_path) -> None:
    # uv reports an interpreter it cannot satisfy through the same "No solution
    # found" headline. Blaming the declared ranges for it would block a release
    # over the resolver's own Python, not over the stack.
    stderr = (
        "  x No solution found when resolving dependencies:\n"
        "  `-> Because the requested Python version (>=3.8) does not satisfy "
        "Python>=3.10 and mcp>=1.27.1 depends on Python>=3.10, we can conclude "
        "that mcp cannot be used.\n"
    )
    runner = FakeRunner(compile_result=(1, "", stderr))
    report = _fresh([_make_repo(tmp_path, "repo-a", compat=BOUNDED)], runner)

    assert "MQC014_FRESH_RESOLVE_UNAVAILABLE" in _codes(report)
    assert "MQC017_RESOLVE_CONFLICT" not in _codes(report)


def test_resolver_targets_the_repository_python(tmp_path) -> None:
    runner = FakeRunner()
    _fresh(
        [_make_repo(tmp_path, "repo-a", compat=BOUNDED, requires_python=">=3.11")],
        runner,
    )

    argv = runner.compiles[0]
    assert "--python-version" in argv
    assert argv[argv.index("--python-version") + 1] == "3.11"


def test_resolver_omits_python_version_when_the_repo_declares_none(tmp_path) -> None:
    runner = FakeRunner()
    _fresh([_make_repo(tmp_path, "repo-a", compat=BOUNDED)], runner)
    assert "--python-version" not in runner.compiles[0]


def test_requested_fresh_resolve_that_could_not_run_is_not_merely_a_warning(
    tmp_path,
) -> None:
    # A repo with no declared boundary already warns statically. If the
    # resolution the caller explicitly asked for never ran, the report must not
    # collapse to that warning and exit 0 as though the dynamic half passed.
    runner = FakeRunner(compile_result=(1, "", OFFLINE_STDERR))
    report = _fresh([_make_repo(tmp_path, "repo-a", compat=None)], runner)

    assert "MQC009_COMPATIBILITY_METADATA_MISSING" in _codes(report)
    assert report["status"] == "UNAVAILABLE"
    # ...and the recommended action addresses the check that did not run, not
    # the warning that happens to also be in the report.
    assert report["next_action"] == (
        "Re-run --fresh-resolve once the package registry is reachable"
    )


def test_a_proven_incompatibility_still_outranks_an_unrun_probe(tmp_path) -> None:
    runner = FakeRunner(
        compile_result=(0, "mcp==2.0.0\n", ""),
        probe_result=(1, "", "ImportError: no fastmcp"),
    )
    entries = [
        _make_repo(tmp_path, "repo-a", declared="mcp>=1.27.1", compat=UNBOUNDED),
        _make_repo(tmp_path, "repo-b", declared="mcp>=1.27.1", compat=UNBOUNDED),
    ]
    report = _fresh(entries, runner)

    assert "MQC016_IMPORT_PROBE_FAILED" in _codes(report)
    assert report["status"] == "FAIL"


def test_a_check_that_did_not_run_outranks_a_repo_with_nothing_to_check(
    tmp_path,
) -> None:
    # A repo with no Python dependency sources is permanently UNAVAILABLE by
    # design. It must not mask the reason the requested resolution failed.
    shell_repo = _make_repo(tmp_path, "repo-shell", declared=None, locked=None)
    runner = FakeRunner(compile_result=(1, "", OFFLINE_STDERR))
    report = _fresh([shell_repo, _make_repo(tmp_path, "repo-a", compat=BOUNDED)], runner)

    assert "MQC004_DEPENDENCY_SOURCE_MISSING" in _codes(report)
    assert report["next_action"] == (
        "Re-run --fresh-resolve once the package registry is reachable"
    )


def test_unavailable_component_is_never_resolved(tmp_path) -> None:
    runner = FakeRunner()
    missing = {"name": "repo-gone", "path": str(tmp_path / "nope"), "role": "test"}
    _fresh([missing], runner)
    assert runner.calls == []


# ── drift between locked and freshly resolved ──────────────────────────────


def test_resolved_version_differing_from_locked_warns(tmp_path) -> None:
    runner = FakeRunner(compile_result=(0, "mcp==1.29.0\n", ""))
    report = _fresh(
        [_make_repo(tmp_path, "repo-a", locked="1.27.1", compat=BOUNDED)], runner
    )

    drift = next(
        f for f in report["findings"] if f["code"] == "MQC015_RESOLVED_DIFFERS_FROM_LOCKED"
    )
    assert drift["severity"] == "WARN"
    assert drift["blocks_release"] is False
    assert "1.29.0" in drift["message"] and "1.27.1" in drift["message"]


def test_matching_locked_and_resolved_raises_nothing(tmp_path) -> None:
    runner = FakeRunner(compile_result=(0, "mcp==1.27.1\n", ""))
    report = _fresh(
        [_make_repo(tmp_path, "repo-a", locked="1.27.1", compat=BOUNDED)], runner
    )
    assert "MQC015_RESOLVED_DIFFERS_FROM_LOCKED" not in _codes(report)


# ── import probes ──────────────────────────────────────────────────────────


def test_import_probe_failure_blocks_release(tmp_path) -> None:
    # The roadmap's regression case: an unbounded range resolves MCP 2.x, the
    # repo is written against the FastMCP 1.x contract, and the import breaks.
    runner = FakeRunner(
        compile_result=(0, "mcp==2.0.0\n", ""),
        probe_result=(1, "", "ModuleNotFoundError: No module named 'mcp.server.fastmcp'"),
    )
    report = _fresh(
        [_make_repo(tmp_path, "repo-a", declared="mcp>=1.27.1", compat=UNBOUNDED)],
        runner,
    )

    probe = next(
        f for f in report["findings"] if f["code"] == "MQC016_IMPORT_PROBE_FAILED"
    )
    assert probe["severity"] == "FAIL"
    assert probe["blocks_release"] is True
    assert report["status"] == "FAIL"


def test_older_lockfile_cannot_make_the_result_green(tmp_path) -> None:
    # repo-a locks a version inside its declared range, so the static gate can
    # only warn — exit code 0. Only the fresh resolution exposes the 2.x it
    # would install today.
    runner = FakeRunner(
        compile_result=(0, "mcp==2.0.0\n", ""),
        probe_result=(
            1,
            "",
            "Traceback (most recent call last):\n  File \"<string>\", line 1\n"
            "ImportError: cannot import name 'FastMCP'\n",
        ),
    )
    entries = [
        _make_repo(tmp_path, "repo-a", declared="mcp>=1.27.1", locked="1.27.1", compat=UNBOUNDED)
    ]
    static = build_report(repos=entries, slice_only=False)
    assert static["status"] == "WARN"

    assert _fresh(entries, runner)["status"] == "FAIL"


def test_probe_failure_from_a_broken_runtime_is_unavailable(tmp_path) -> None:
    runner = FakeRunner(
        compile_result=(0, "mcp==1.27.1\n", ""),
        probe_result=(2, "", "error: Failed to fetch: the network was disabled"),
    )
    report = _fresh([_make_repo(tmp_path, "repo-a", compat=BOUNDED)], runner)

    assert "MQC014_FRESH_RESOLVE_UNAVAILABLE" in _codes(report)
    assert "MQC016_IMPORT_PROBE_FAILED" not in _codes(report)


def test_environment_build_failure_is_not_a_broken_import(tmp_path) -> None:
    # uv failing to build a wheel says nothing about the repository's import.
    runner = FakeRunner(
        compile_result=(0, "mcp==1.27.1\n", ""),
        probe_result=(
            1,
            "",
            "  x Failed to build `mcp==1.27.1`\n"
            "  |-> The build backend returned an error\n",
        ),
    )
    report = _fresh([_make_repo(tmp_path, "repo-a", compat=BOUNDED)], runner)

    assert "MQC016_IMPORT_PROBE_FAILED" not in _codes(report)
    assert "MQC014_FRESH_RESOLVE_UNAVAILABLE" in _codes(report)


def test_a_syntax_error_in_the_declared_probe_is_reported(tmp_path) -> None:
    # Python failures do not all print a traceback; a broken probe statement
    # must still be attributable to the repository that declared it.
    runner = FakeRunner(
        compile_result=(0, "mcp==1.27.1\n", ""),
        probe_result=(
            1,
            "",
            '  File "<string>", line 1\n    def (\n        ^\nSyntaxError: invalid syntax\n',
        ),
    )
    report = _fresh([_make_repo(tmp_path, "repo-a", compat=BOUNDED)], runner)
    assert "MQC016_IMPORT_PROBE_FAILED" in _codes(report)


def test_probe_key_is_matched_by_canonical_name(tmp_path) -> None:
    runner = FakeRunner()
    compat = dict(BOUNDED, import_probes={"MCP": "import mcp"})
    _fresh([_make_repo(tmp_path, "repo-a", compat=compat)], runner)

    assert runner.probes, "a differently spelled key silently skipped the probe"
    assert "import mcp" in runner.probes[0]


def test_probe_statement_is_declared_by_the_repository(tmp_path) -> None:
    runner = FakeRunner()
    compat = dict(BOUNDED, import_probes={"mcp": "import mcp; mcp.repo_specific()"})
    _fresh([_make_repo(tmp_path, "repo-a", compat=compat)], runner)

    assert runner.probes, "no probe was run"
    assert "import mcp; mcp.repo_specific()" in runner.probes[0]


def test_probe_runs_the_freshly_resolved_pin(tmp_path) -> None:
    runner = FakeRunner(compile_result=(0, "mcp==1.29.0\n", ""))
    _fresh([_make_repo(tmp_path, "repo-a", compat=BOUNDED)], runner)

    assert "mcp==1.29.0" in runner.probes[0]


def test_no_probe_is_run_without_a_declared_statement(tmp_path) -> None:
    runner = FakeRunner()
    compat = {"dependencies": {"mcp": ">=1.27.1,<2"}, "import_probes": {}}
    _fresh([_make_repo(tmp_path, "repo-a", compat=compat)], runner)

    assert runner.compiles
    assert runner.probes == []


# ── the working tree is never touched ──────────────────────────────────────


def test_fresh_resolve_never_works_inside_the_repository(tmp_path) -> None:
    entry = _make_repo(tmp_path, "repo-a", compat=BOUNDED)
    repo = Path(entry["path"])
    before = {p: p.read_bytes() for p in sorted(repo.rglob("*")) if p.is_file()}

    runner = FakeRunner()
    _fresh([entry], runner)

    for argv, cwd, _ in runner.calls:
        assert not cwd.is_relative_to(repo), f"ran inside the repo: {argv}"
    after = {p: p.read_bytes() for p in sorted(repo.rglob("*")) if p.is_file()}
    assert after == before


def test_temporary_directory_is_removed_after_the_run(tmp_path) -> None:
    runner = FakeRunner()
    _fresh([_make_repo(tmp_path, "repo-a", compat=BOUNDED)], runner)

    assert runner.calls
    for _, cwd, _ in runner.calls:
        assert not cwd.exists()


# ── CLI ────────────────────────────────────────────────────────────────────


def test_cli_flag_reaches_the_resolver(monkeypatch) -> None:
    from typer.testing import CliRunner

    import mq_agent.tools.stack_compatibility as module
    from mq_agent.main import app

    seen: dict[str, Any] = {}

    def _fake(repos=None, tracked=("mcp",), slice_only=True, fresh_resolve=False):
        seen["fresh_resolve"] = fresh_resolve
        return json.dumps(
            {
                "schema": "mq.stack-compatibility.v1",
                "status": "PASS",
                "mode": "fresh-resolve" if fresh_resolve else "static",
                "components": [],
                "relationships": [],
                "findings": [],
                "next_action": "",
                "checked_at": "2026-08-13T00:00:00+00:00",
            }
        )

    monkeypatch.setattr(module, "stack_compatibility", _fake)
    result = CliRunner().invoke(app, ["stack", "compatibility", "--fresh-resolve", "--json"])

    assert result.exit_code == 0
    assert seen["fresh_resolve"] is True
    assert json.loads(result.stdout)["mode"] == "fresh-resolve"
