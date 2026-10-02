"""Contract tests for exact-head stack status v2."""
from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.branch_protection_contract import GITHUB_ACTIONS_APP_ID
from mq_agent.tools.stack_status import build_stack_status_v2

runner = CliRunner()
APP = GITHUB_ACTIONS_APP_ID
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


class FakeGh:
    def __init__(self, payload=None, error: Exception | None = None):
        self.payload = payload or {"check_runs": []}
        self.error = error
        self.calls: list[tuple[str, ...]] = []

    def json(self, *args: str):
        self.calls.append(args)
        if self.error:
            raise self.error
        return self.payload


def _repo(tmp_path: Path, *, dirty: bool = False) -> tuple[dict[str, str], str]:
    path = tmp_path / "demo"
    path.mkdir()
    (path / "VERSION").write_text("1.0.0\n")
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(["git", "add", "VERSION"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()
    if dirty:
        (path / "dirty.txt").write_text("local change\n")
    return {"name": "demo", "path": str(path), "role": "test"}, sha


def _contract():
    return {
        "schema": "mq.branch-protection-contract.v1",
        "owner": "MCamner",
        "branch": "main",
        "repos": {
            "demo": {
                "required_checks": [
                    {"name": "test", "app_id": APP},
                    {"name": "markdownlint", "app_id": APP},
                ]
            }
        },
    }


def _run(name: str, *, conclusion: str = "success", completed_at: str | None = None):
    stamp = completed_at or (NOW - timedelta(minutes=5)).isoformat()
    return {
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "completed_at": stamp,
        "details_url": f"https://example.invalid/{name}",
        "app": {"id": APP},
    }


def _status(tmp_path: Path, *, gh: FakeGh, dirty: bool = False, age=3600):
    entry, _ = _repo(tmp_path, dirty=dirty)
    return build_stack_status_v2(
        gh=gh,
        contract=_contract(),
        repos=[entry],
        now=NOW,
        max_age_seconds=age,
    )


def test_fresh_exact_head_with_all_required_checks_is_verified(tmp_path):
    data = _status(tmp_path, gh=FakeGh({"check_runs": [_run("test"), _run("markdownlint")]}))
    repo = data["repos"][0]
    assert data["schema"] == "mq.stack-status.v2"
    assert data["overall"] == "VERIFIED"
    assert repo["verification"]["status"] == "VERIFIED"
    assert repo["verification"]["verified_count"] == 2
    assert repo["verification"]["required_count"] == 2
    assert repo["verification"]["reason"] == "all-required-checks-passed"


def test_query_is_for_the_exact_local_head(tmp_path):
    entry, sha = _repo(tmp_path)
    gh = FakeGh({"check_runs": [_run("test"), _run("markdownlint")]})
    build_stack_status_v2(
        gh=gh, contract=_contract(), repos=[entry], now=NOW, max_age_seconds=3600
    )
    assert gh.calls == [
        ("api", f"repos/MCamner/demo/commits/{sha}/check-runs?per_page=100")
    ]


def test_missing_required_check_is_unverified_not_assumed_green(tmp_path):
    data = _status(tmp_path, gh=FakeGh({"check_runs": [_run("test")]}))
    verification = data["repos"][0]["verification"]
    assert verification["status"] == "UNVERIFIED"
    assert verification["scopes"][1]["status"] == "MISSING"
    assert "markdownlint" in verification["reason"]


def test_failed_required_check_is_fail(tmp_path):
    data = _status(
        tmp_path,
        gh=FakeGh({"check_runs": [_run("test", conclusion="failure"), _run("markdownlint")]}),
    )
    assert data["overall"] == "FAIL"
    assert data["repos"][0]["verification"]["status"] == "FAIL"


def test_complete_green_evidence_becomes_stale(tmp_path):
    old = (NOW - timedelta(days=2)).isoformat()
    data = _status(
        tmp_path,
        gh=FakeGh({"check_runs": [
            _run("test", completed_at=old),
            _run("markdownlint", completed_at=old),
        ]}),
        age=86400,
    )
    verification = data["repos"][0]["verification"]
    assert verification["status"] == "STALE"
    assert verification["age_seconds"] == 172800


def test_dirty_worktree_is_not_called_verified(tmp_path):
    data = _status(
        tmp_path,
        dirty=True,
        gh=FakeGh({"check_runs": [_run("test"), _run("markdownlint")]}),
    )
    verification = data["repos"][0]["verification"]
    assert verification["status"] == "UNVERIFIED"
    assert verification["reason"] == "working-tree-dirty"


def test_github_failure_degrades_to_unverified_without_fabrication(tmp_path):
    data = _status(tmp_path, gh=FakeGh(error=RuntimeError("offline")))
    verification = data["repos"][0]["verification"]
    assert verification["status"] == "UNVERIFIED"
    assert verification["verified_count"] == 0
    assert verification["scopes"] == []
    assert verification["reason"] == "github-unavailable: offline"


def test_missing_repo_is_unverified_and_does_not_query_github(tmp_path):
    gh = FakeGh()
    entry = {"name": "demo", "path": str(tmp_path / "missing"), "role": "test"}
    data = build_stack_status_v2(
        gh=gh, contract=_contract(), repos=[entry], now=NOW, max_age_seconds=3600
    )
    assert data["repos"][0]["verification"]["status"] == "UNVERIFIED"
    assert data["repos"][0]["verification"]["reason"] == "repo-not-found"
    assert gh.calls == []


def test_output_matches_checked_in_schema(tmp_path):
    data = _status(tmp_path, gh=FakeGh({"check_runs": [_run("test"), _run("markdownlint")]}))
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "mq_stack_status_v2.schema.json"
    schema = json.loads(schema_path.read_text())
    Draft202012Validator(schema).validate(data)


def test_cli_json_returns_v2_document(monkeypatch):
    payload = {
        "schema": "mq.stack-status.v2",
        "checked_at": NOW.isoformat(),
        "max_age_seconds": 86400,
        "overall": "VERIFIED",
        "repos": [],
    }
    monkeypatch.setattr(
        "mq_agent.tools.stack_status.stack_status_v2",
        lambda: json.dumps(payload),
    )
    result = runner.invoke(app, ["stack", "status", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == payload
