"""`mq-agent pr review <number>`: an advisory, read-only review of a pull request.

The PR is fetched into a temporary detached worktree, each changed file is
classified by path and size, the repo's own `verify-changes` selection is
planned against the merge base, and one report is produced. Nothing in the PR
is executed, and nothing is posted unless `--post` is given.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools import pr_review
from mq_agent.tools.pr_review import classify_file, render_markdown, review_pr

runner = CliRunner()

CONFIG = {
    "schema": "mq.verification-config.v1",
    "checks": [
        {"id": "unit", "runner": "bash", "targets": ["check.sh"],
         "paths": ["src/*", "tests/*"], "timeout_seconds": 30},
    ],
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _write(repo: Path, name: str, text: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def pr_repo(tmp_path: Path) -> dict[str, Any]:
    """A clone whose origin has `main` and `refs/pull/7/head`."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    _write(seed, ".mq/verification.json", json.dumps(CONFIG))
    _write(seed, "check.sh", "exit 0\n")
    _write(seed, "src/app.py", "x = 1\n")
    _write(seed, "README.md", "# r\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-q", "-m", "base")
    base = _git(seed, "rev-parse", "HEAD")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "origin", "main")

    _git(seed, "checkout", "-q", "-b", "feature")
    _write(seed, "src/app.py", "x = 2\n")
    _write(seed, "docs/guide.md", "guide\n")
    _write(seed, ".github/workflows/ci.yml", "on: push\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-q", "-m", "change")
    head = _git(seed, "rev-parse", "HEAD")
    _git(seed, "push", "-q", "origin", "feature:refs/pull/7/head")

    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
    return {"repo": clone, "base": base, "head": head, "state": tmp_path / "state"}


def _meta(pr: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    meta = {
        "number": 7, "title": "Change app", "url": "https://example.invalid/pull/7",
        "state": "OPEN", "isDraft": False, "baseRefName": "main",
        "baseRefOid": pr["base"], "headRefOid": pr["head"],
        "files": [
            {"path": "src/app.py", "additions": 1, "deletions": 1, "changeType": "MODIFIED"},
            {"path": "docs/guide.md", "additions": 1, "deletions": 0, "changeType": "ADDED"},
            {"path": ".github/workflows/ci.yml", "additions": 1, "deletions": 0, "changeType": "ADDED"},
        ],
    }
    meta.update(overrides)
    return meta


@pytest.fixture
def fake_gh(monkeypatch):
    calls: list[list[str]] = []
    state: dict[str, Any] = {}

    def gh(args: list[str], cwd: Path) -> str:
        calls.append(args)
        if args[:2] == ["pr", "view"]:
            return json.dumps(state["meta"])
        if args[:2] == ["pr", "comment"]:
            return "https://example.invalid/pull/7#comment"
        raise AssertionError(f"unexpected gh call {args}")

    monkeypatch.setattr(pr_review, "_gh", gh)
    return calls, state


# ── classification ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("path,level", [
    (".github/workflows/ci.yml", "high"),
    ("schemas/context_pack.schema.json", "high"),
    ("api/thing.schema.json", "high"),
    (".mq/verification.json", "high"),
    ("release-check.sh", "high"),
    ("pyproject.toml", "high"),
    ("uv.lock", "high"),
    (".claude/settings.json", "high"),
    ("mq_agent/main.py", "medium"),
    ("scripts/build.sh", "medium"),
    ("tests/test_app.py", "low"),
    ("pkg/app_test.py", "low"),
    ("docs/guide.md", "low"),
    ("README.md", "low"),
])
def test_files_are_classified_by_path(path, level):
    assert classify_file(path, additions=1, deletions=0, change="MODIFIED")["risk"] == level


def test_a_large_low_risk_change_is_raised_to_medium():
    item = classify_file("tests/test_big.py", additions=450, deletions=0, change="MODIFIED")
    assert item["risk"] == "medium"
    assert any("450" in r for r in item["reasons"])


def test_deleting_source_is_at_least_medium():
    assert classify_file("README.md", additions=0, deletions=5, change="DELETED")["risk"] == "low"
    assert classify_file("src/a.py", additions=0, deletions=5, change="DELETED")["risk"] == "medium"


# ── end to end against a real clone ─────────────────────────────────────────

def test_review_reports_risk_planned_checks_and_what_was_not_verified(pr_repo, fake_gh):
    _, state = fake_gh
    state["meta"] = _meta(pr_repo)

    report = review_pr(pr_repo["repo"], 7, state_dir=pr_repo["state"])

    assert report["schema"] == "mq.pr-review.v1"
    assert report["pr"]["head"] == pr_repo["head"]
    assert report["merge_base"] == pr_repo["base"]
    assert report["risk"] == "high"
    assert {f["path"]: f["risk"] for f in report["files"]} == {
        "src/app.py": "medium", "docs/guide.md": "low", ".github/workflows/ci.yml": "high",
    }
    assert [c["id"] for c in report["recommended_checks"]] == ["unit"]
    assert set(report["uncovered_files"]) == {"docs/guide.md", ".github/workflows/ci.yml"}
    assert any("without test changes" in f for f in report["findings"])
    assert "planned checks were not run" in " ".join(report["not_verified"])
    assert report["posted"] is None


def test_review_leaves_no_worktree_and_no_receipt_behind(pr_repo, fake_gh):
    _, state = fake_gh
    state["meta"] = _meta(pr_repo)

    review_pr(pr_repo["repo"], 7, state_dir=pr_repo["state"])

    worktrees = _git(pr_repo["repo"], "worktree", "list", "--porcelain")
    assert worktrees.count("worktree ") == 1
    assert not list(pr_repo["state"].rglob("*")) or not any(
        p.is_file() for p in pr_repo["state"].rglob("*")
    )
    assert _git(pr_repo["repo"], "status", "--porcelain") == ""


def test_a_head_that_moved_after_gh_answered_is_refused(pr_repo, fake_gh):
    _, state = fake_gh
    state["meta"] = _meta(pr_repo, headRefOid="0" * 40)

    with pytest.raises(ValueError, match="moved"):
        review_pr(pr_repo["repo"], 7, state_dir=pr_repo["state"])


def test_a_pr_that_changes_its_own_verification_config_is_flagged(pr_repo, fake_gh):
    _, state = fake_gh
    meta = _meta(pr_repo)
    meta["files"].append({"path": ".mq/verification.json", "additions": 1,
                          "deletions": 1, "changeType": "MODIFIED"})
    state["meta"] = meta

    report = review_pr(pr_repo["repo"], 7, state_dir=pr_repo["state"])

    assert any("verification config" in f for f in report["findings"])


def test_markdown_report_names_risk_checks_and_limits(pr_repo, fake_gh):
    _, state = fake_gh
    state["meta"] = _meta(pr_repo)
    text = render_markdown(review_pr(pr_repo["repo"], 7, state_dir=pr_repo["state"]))

    assert "Risk: **high**" in text
    assert "`.github/workflows/ci.yml`" in text
    assert "`unit`" in text
    assert "Not verified" in text


# ── CLI ─────────────────────────────────────────────────────────────────────

def _cli(pr_repo, *extra: str):
    return runner.invoke(app, ["pr", "review", "7", "--repo", str(pr_repo["repo"]),
                               "--state-dir", str(pr_repo["state"]), *extra])


def test_cli_json_does_not_post(pr_repo, fake_gh):
    calls, state = fake_gh
    state["meta"] = _meta(pr_repo)

    result = _cli(pr_repo, "--json")

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["risk"] == "high"
    assert not any(c[:2] == ["pr", "comment"] for c in calls)


def test_cli_post_comments_once_with_the_markdown_report(pr_repo, fake_gh):
    calls, state = fake_gh
    state["meta"] = _meta(pr_repo)

    result = _cli(pr_repo, "--post", "--json")

    assert result.exit_code == 0, result.output
    comments = [c for c in calls if c[:2] == ["pr", "comment"]]
    assert len(comments) == 1
    assert json.loads(result.stdout)["posted"] == "https://example.invalid/pull/7#comment"


def test_cli_reports_errors_with_exit_2(pr_repo, fake_gh):
    _, state = fake_gh
    state["meta"] = _meta(pr_repo, headRefOid="0" * 40)

    assert _cli(pr_repo).exit_code == 2


def test_a_hung_git_or_gh_is_an_error_not_a_traceback(monkeypatch, tmp_path):
    def hang(*a, **k):
        raise subprocess.TimeoutExpired(cmd="gh", timeout=60)

    monkeypatch.setattr(pr_review.subprocess, "run", hang)
    with pytest.raises(ValueError, match="failed"):
        pr_review._gh(["pr", "view"], tmp_path)
    with pytest.raises(ValueError, match="failed"):
        pr_review._git(tmp_path, "fetch")


# ── phase 2: model review through mq-mcp review_patch ───────────────────────

def _wire(payload: dict) -> list:
    """The shape mq-mcp's HTTP endpoint returns: one text item holding JSON."""
    return [{"type": "text", "text": json.dumps(payload)}]


class _Reviewer:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, patch: str, mode: str, label: str) -> Any:
        self.calls.append((patch, mode, label))
        return self.result


OK_REVIEW = {
    "ok": True, "mode": "risk", "label": "clone#7", "model": "qwen3.5:9b",
    "reviewed_bytes": 10,
    "findings": [{"severity": "RISK", "location": "src/app.py:1", "body": "Changed constant."}],
    "output": "[RISK] src/app.py:1\nChanged constant.",
}


def test_without_model_review_nothing_is_sent(pr_repo, fake_gh):
    _, state = fake_gh
    state["meta"] = _meta(pr_repo)

    report = review_pr(pr_repo["repo"], 7, state_dir=pr_repo["state"])

    assert report["model_review"] is None
    assert any("no model review" in n for n in report["not_verified"])


def test_model_review_sends_the_pr_diff_and_reports_findings(pr_repo, fake_gh):
    _, state = fake_gh
    state["meta"] = _meta(pr_repo)
    reviewer = _Reviewer(_wire(OK_REVIEW))

    report = review_pr(pr_repo["repo"], 7, state_dir=pr_repo["state"], reviewer=reviewer)

    patch, mode, label = reviewer.calls[0]
    assert "+x = 2" in patch and "docs/guide.md" in patch
    assert mode == "risk"
    assert label == "clone#7"
    review = report["model_review"]
    assert review["status"] == "OK"
    assert review["model"] == "qwen3.5:9b"
    assert review["findings"] == OK_REVIEW["findings"]
    assert any("saw only the diff" in n for n in report["not_verified"])
    assert not any("no model review" in n for n in report["not_verified"])
    # The model's view does not change the path-based risk.
    assert report["risk"] == "high"


def test_a_plain_dict_answer_is_accepted_too(pr_repo, fake_gh):
    _, state = fake_gh
    state["meta"] = _meta(pr_repo)

    report = review_pr(pr_repo["repo"], 7, state_dir=pr_repo["state"],
                       reviewer=_Reviewer(OK_REVIEW))

    assert report["model_review"]["status"] == "OK"


def test_a_refused_or_unreachable_review_is_an_error_not_a_pass(pr_repo, fake_gh):
    _, state = fake_gh
    state["meta"] = _meta(pr_repo)
    for answer in (_wire({"ok": False, "error": "patch too large"}),
                   "mq-mcp is not reachable", None):
        report = review_pr(pr_repo["repo"], 7, state_dir=pr_repo["state"],
                           reviewer=_Reviewer(answer))
        assert report["model_review"]["status"] == "ERROR"
        assert report["model_review"]["findings"] == []
        assert any("no model review" in n for n in report["not_verified"])


def test_an_oversized_diff_is_not_sent(pr_repo, fake_gh, monkeypatch):
    _, state = fake_gh
    state["meta"] = _meta(pr_repo)
    monkeypatch.setattr(pr_review, "REVIEW_PATCH_MAX_BYTES", 10)
    reviewer = _Reviewer(_wire(OK_REVIEW))

    report = review_pr(pr_repo["repo"], 7, state_dir=pr_repo["state"], reviewer=reviewer)

    assert reviewer.calls == []
    assert report["model_review"]["status"] == "SKIPPED"
    assert "bytes" in report["model_review"]["reason"]


def test_markdown_shows_model_findings_as_advisory(pr_repo, fake_gh):
    _, state = fake_gh
    state["meta"] = _meta(pr_repo)
    report = review_pr(pr_repo["repo"], 7, state_dir=pr_repo["state"],
                       reviewer=_Reviewer(_wire(OK_REVIEW)))

    text = render_markdown(report)

    assert "### Model review (advisory)" in text
    assert "`src/app.py:1`" in text and "Changed constant." in text
    assert "qwen3.5:9b" in text


def test_cli_model_review_uses_the_mq_mcp_bridge(pr_repo, fake_gh, monkeypatch):
    _, state = fake_gh
    state["meta"] = _meta(pr_repo)
    sent: list = []

    class _Bridge:
        def review_patch(self, patch: str, mode: str = "risk", label: str = "") -> Any:
            sent.append((mode, label))
            return _wire(OK_REVIEW)

    monkeypatch.setattr("mq_agent.tools.mcp_bridge.MultiMCPBridge", _Bridge)

    result = _cli(pr_repo, "--model-review", "--review-mode", "security", "--json")

    assert result.exit_code == 0, result.output
    assert sent == [("security", "clone#7")]
    assert json.loads(result.stdout)["model_review"]["status"] == "OK"
