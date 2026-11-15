"""Advisory, read-only review of one pull request (`mq-agent pr review`).

The PR head is fetched into a temporary detached worktree, every changed file
is classified by path and size, and the repository's own `verify-changes`
selection is planned against the merge base. Nothing from the PR is executed:
the planned checks come from configuration the PR itself can change, so running
them would run the PR's code under the PR's own rules. With a reviewer, the
PR's diff is sent as text to mq-mcp `review_patch` for an advisory model
review; the model sees only the diff, and its findings never change the
path-based risk.

Path classification is a heuristic for where a reviewer should look first, not
a verdict on the change.
"""
from __future__ import annotations

import fnmatch
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from collections.abc import Callable
from typing import Any

SCHEMA = "mq.pr-review.v1"
RISK_ORDER = ("low", "medium", "high")
LARGE_FILE_LINES = 400
LARGE_PR_LINES = 1000
#: Mirrors mq-mcp review_patch's limit, so an oversized diff is not sent at all.
REVIEW_PATCH_MAX_BYTES = 200_000
REVIEW_MODES = ("risk", "security", "architecture", "comment")

Reviewer = Callable[[str, str, str], Any]

# First match wins. Each rule: (patterns, risk, reason).
_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    ((".github/workflows/*",), "high", "CI or release automation"),
    (("schemas/*", "*.schema.json"), "high", "contract schema"),
    ((".mq/*",), "high", "repo contract or verification config"),
    (("release*.sh", "scripts/release*", "VERSION"), "high", "release surface"),
    (("pyproject.toml", "uv.lock", "package.json", "package-lock.json",
      "requirements*.txt", "setup.py", "setup.cfg"), "high", "dependencies or packaging"),
    ((".claude/settings*", ".githooks/*", "hooks/*", ".codex/*"), "high",
     "agent permissions or git hooks"),
    (("tests/*", "test_*.py", "*/test_*.py", "*_test.py", "*_test.go", "*.test.ts",
      "*.test.js"), "low", "tests"),
    (("*.md", "docs/*", "*.txt", "LICENSE*"), "low", "documentation"),
)


def _risk_max(levels: list[str]) -> str:
    return max(levels, key=RISK_ORDER.index) if levels else "low"


def _match(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(path, p) for p in patterns)


def classify_file(path: str, *, additions: int, deletions: int, change: str) -> dict[str, Any]:
    """Risk for one changed file: path rule first, then size and deletion."""
    risk, reasons = "medium", ["source"]
    for patterns, rule_risk, reason in _RULES:
        if _match(path, patterns):
            risk, reasons = rule_risk, [reason]
            break
    lines = additions + deletions
    if lines > LARGE_FILE_LINES and risk == "low":
        risk = "medium"
        reasons.append(f"{lines} changed lines")
    if change == "DELETED" and risk == "low" and "documentation" not in reasons:
        risk = "medium"
        reasons.append("file deleted")
    if change == "DELETED" and "source" in reasons:
        reasons.append("file deleted")
    return {"path": path, "risk": risk, "reasons": reasons, "change": change,
            "additions": additions, "deletions": deletions}


def _gh(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(["gh", *args], cwd=cwd, capture_output=True, text=True,
                                check=False, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"gh {' '.join(args[:2])} failed: {exc}") from exc
    if result.returncode != 0:
        raise ValueError(f"gh {' '.join(args[:2])} failed: {result.stderr.strip()}")
    return result.stdout


def _git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                                text=True, check=False, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"git {args[0]} failed: {exc}") from exc
    if result.returncode != 0:
        raise ValueError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


_PR_FIELDS = "number,title,url,state,isDraft,baseRefName,baseRefOid,headRefOid,files"


def _findings(files: list[dict[str, Any]], plan: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    paths = [f["path"] for f in files]
    if ".mq/verification.json" in paths:
        findings.append(
            "the PR changes its own verification config, so the recommended checks "
            "come from the PR; compare them with the base branch's selection"
        )
    source = [f["path"] for f in files if "source" in f["reasons"]]
    tests = [f["path"] for f in files if "tests" in f["reasons"]]
    if source and not tests:
        findings.append(f"source changed without test changes: {', '.join(source)}")
    if plan["uncovered_files"]:
        findings.append(
            "no verification check covers: " + ", ".join(plan["uncovered_files"])
        )
    total = sum(f["additions"] + f["deletions"] for f in files)
    if total > LARGE_PR_LINES:
        findings.append(f"large change: {total} changed lines")
    return findings


def _review_payload(result: Any) -> dict[str, Any] | None:
    """The review_patch answer as a dict, from a dict or mq-mcp's text wrapper."""
    if isinstance(result, dict) and "ok" in result:
        return result
    if isinstance(result, list):
        for item in result:
            payload = _review_payload(item)
            if payload is not None:
                return payload
            if isinstance(item, dict) and item.get("type") == "text":
                try:
                    parsed = json.loads(item.get("text") or "")
                except ValueError:
                    continue
                if isinstance(parsed, dict) and "ok" in parsed:
                    return parsed
    return None


def _model_review(patch: str, reviewer: Reviewer, mode: str, label: str) -> dict[str, Any]:
    size = len(patch.encode("utf-8"))
    if size > REVIEW_PATCH_MAX_BYTES:
        return {"status": "SKIPPED", "mode": mode, "findings": [],
                "reason": f"diff is {size} bytes; review_patch accepts at most "
                          f"{REVIEW_PATCH_MAX_BYTES}"}
    try:
        answer = reviewer(patch, mode, label)
    except Exception as exc:  # the bridge reports most failures as values
        answer = f"review_patch failed: {exc}"
    payload = _review_payload(answer)
    if payload is None or not payload.get("ok"):
        error = (payload or {}).get("error") or str(answer)[:300] or "no answer"
        return {"status": "ERROR", "mode": mode, "findings": [], "error": error}
    return {
        "status": "OK",
        "mode": payload.get("mode", mode),
        "model": payload.get("model"),
        "reviewed_bytes": payload.get("reviewed_bytes", size),
        "findings": [
            {"severity": str(f.get("severity", "")), "location": str(f.get("location", "")),
             "body": str(f.get("body", ""))}
            for f in payload.get("findings") or [] if isinstance(f, dict)
        ],
    }


def review_pr(
    repo: Path,
    number: int,
    *,
    state_dir: Path | None = None,
    reviewer: Reviewer | None = None,
    review_mode: str = "risk",
) -> dict[str, Any]:
    """Build the review report for PR `number` of the repository at `repo`.

    Raises ValueError when the PR cannot be fetched, or when its head on the
    remote is not the head GitHub reported, so the report always describes the
    commit it names.
    """
    from mq_agent.verify_changes import verify

    repo = Path(_git(Path(repo), "rev-parse", "--show-toplevel"))
    meta = json.loads(_gh(["pr", "view", str(number), "--json", _PR_FIELDS], repo))
    head = meta["headRefOid"]
    base_ref = meta["baseRefName"]

    _git(repo, "fetch", "--quiet", "origin",
         f"+refs/pull/{number}/head:refs/mq-pr-review/{number}",
         f"+refs/heads/{base_ref}:refs/mq-pr-review/{number}-base")
    try:
        fetched = _git(repo, "rev-parse", f"refs/mq-pr-review/{number}^{{commit}}")
        if fetched != head:
            raise ValueError(
                f"PR #{number} head moved: GitHub reported {head[:12]}, "
                f"origin has {fetched[:12]}; rerun the review"
            )
        merge_base = _git(repo, "merge-base", head, f"refs/mq-pr-review/{number}-base")
        patch = (
            _git(repo, "diff", "--no-color", "--no-ext-diff", merge_base, head) + "\n"
            if reviewer is not None else ""
        )

        root = Path(state_dir).expanduser() if state_dir else None
        if root is not None:
            root.mkdir(parents=True, exist_ok=True)
        workdir = Path(tempfile.mkdtemp(prefix=f"pr-{number}-", dir=root))
        worktree = workdir / "tree"
        _git(repo, "worktree", "add", "--quiet", "--detach", str(worktree), head)
        try:
            plan = verify(worktree, base=merge_base, plan_only=True)
        finally:
            _git(repo, "worktree", "remove", "--force", str(worktree))
            shutil.rmtree(workdir, ignore_errors=True)
    finally:
        for ref in (f"refs/mq-pr-review/{number}", f"refs/mq-pr-review/{number}-base"):
            subprocess.run(["git", "-C", str(repo), "update-ref", "-d", ref],
                           capture_output=True, check=False)

    model_review = (
        _model_review(patch, reviewer, review_mode, f"{repo.name}#{number}")
        if reviewer is not None else None
    )
    if model_review is None:
        model_note = "no model review of the diff"
    elif model_review["status"] == "OK":
        model_note = ("the model review saw only the diff, not the files around it; "
                      "its findings are advisory and can be false positives")
    else:
        reason = model_review.get("reason") or model_review.get("error")
        model_note = f"no model review of the diff: {reason}"

    files = [
        classify_file(f["path"], additions=int(f.get("additions") or 0),
                      deletions=int(f.get("deletions") or 0),
                      change=str(f.get("changeType") or "MODIFIED"))
        for f in meta.get("files") or []
    ]
    return {
        "schema": SCHEMA,
        "pr": {"number": meta["number"], "title": meta["title"], "url": meta["url"],
               "state": meta["state"], "draft": bool(meta.get("isDraft")),
               "base": base_ref, "head": head},
        "merge_base": merge_base,
        "risk": _risk_max([f["risk"] for f in files]),
        "files": files,
        "recommended_checks": [
            {"id": c["id"], "runner": c["runner"], "targets": c["targets"]}
            for c in plan["checks"]
        ],
        "uncovered_files": plan["uncovered_files"],
        "findings": _findings(files, plan),
        "model_review": model_review,
        "not_verified": [
            "planned checks were not run: they come from configuration the PR can change",
            model_note,
            "risk is a path and size heuristic, not a judgment of the change",
        ],
        "posted": None,
    }


def render_markdown(report: dict[str, Any]) -> str:
    pr = report["pr"]
    lines = [
        f"## mq-agent PR review — #{pr['number']}",
        "",
        f"Risk: **{report['risk']}** · head `{pr['head'][:12]}` · merge base "
        f"`{report['merge_base'][:12]}`",
        "",
        "### Files",
        "",
        "| Risk | File | Why |",
        "| --- | --- | --- |",
    ]
    ordered = sorted(report["files"], key=lambda f: -RISK_ORDER.index(f["risk"]))
    lines += [f"| {f['risk']} | `{f['path']}` | {', '.join(f['reasons'])} |" for f in ordered]
    lines += ["", "### Recommended checks", ""]
    lines += [f"- `{c['id']}` ({c['runner']}): {', '.join(c['targets'])}"
              for c in report["recommended_checks"]] or ["- none selected"]
    if report["findings"]:
        lines += ["", "### Findings", ""]
        lines += [f"- {f}" for f in report["findings"]]
    review = report.get("model_review")
    if review is not None:
        lines += ["", "### Model review (advisory)", ""]
        if review["status"] == "OK":
            lines.append(f"`{review['mode']}` review by {review.get('model') or 'unknown model'}"
                         f" of {review.get('reviewed_bytes')} bytes of diff.")
            lines.append("")
            lines += [f"- **{f['severity']}** `{f['location']}`: {f['body']}"
                      for f in review["findings"]] or ["- no findings"]
        else:
            lines.append(f"{review['status']}: {review.get('reason') or review.get('error')}")
    lines += ["", "### Not verified", ""]
    lines += [f"- {n}" for n in report["not_verified"]]
    return "\n".join(lines) + "\n"


def post_report(repo: Path, number: int, report: dict[str, Any]) -> str:
    """Post the report as one PR comment and return what gh printed (its URL)."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(render_markdown(report))
        body = Path(fh.name)
    try:
        return _gh(["pr", "comment", str(number), "--body-file", str(body)], Path(repo)).strip()
    finally:
        body.unlink(missing_ok=True)
