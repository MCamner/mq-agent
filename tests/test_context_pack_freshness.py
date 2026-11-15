"""A task pack records what it was built from, and `context check` says
whether that still holds.

The pack is read by Claude and Codex as "the minimum context for this task".
A pack built before the repo or the vault moved can point an agent at state
that no longer exists, so the check answers FRESH only when every recorded
input is unchanged, STALE when one moved, and UNKNOWN when it cannot tell.
UNKNOWN is never reported as FRESH or STALE.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.context_pack import build_task_pack, check_task_pack

runner = CliRunner()

CARD = """---
schema: context-card.v1
repo: mq-mcp
---

# Context Card: mq-mcp
"""

VOCABULARY = {
    "schema": "context-selection-vocabulary.v1",
    "source_heavy_hints": ["caller"],
    "source_heavy_suppress": ["readme"],
    "max_codegraph_queries": 5,
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(repo: Path, name: str, text: str) -> None:
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", name)


def _init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A git vault with one card, and a git repo `mq-mcp` with a contract."""
    vault = tmp_path / "mqobsidian"
    _init(vault)
    (vault / "memory" / "context-cards").mkdir(parents=True)
    (vault / ".mq").mkdir()
    (vault / ".mq" / "context-selection-vocabulary.json").write_text(json.dumps(VOCABULARY))
    (vault / "memory" / "context-cards" / "mq-mcp-card.md").write_text(CARD)
    _git(vault, "add", ".")
    _git(vault, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "v")

    root = tmp_path / "repos"
    repo = root / "mq-mcp"
    _init(repo)
    (repo / ".mq").mkdir()
    _commit(repo, ".mq/repo-contract.json", json.dumps({"repo": "mq-mcp", "version": "1.2.0"}))
    return vault, root, repo


def _pack(tmp_path: Path, vault: Path, root: Path, **kw) -> Path:
    content = build_task_pack("update docs", repo="mq-mcp", vault=vault, repos_root=root, **kw)[
        "content"
    ]
    path = tmp_path / "task-pack.md"
    path.write_text(content, encoding="utf-8")
    return path


def _frontmatter(path: Path) -> dict[str, str]:
    block = path.read_text(encoding="utf-8").split("---\n", 2)[1]
    return dict(line.split(": ", 1) for line in block.splitlines() if line.strip())


def test_the_pack_records_what_it_was_built_from(tmp_path):
    vault, root, repo = _setup(tmp_path)
    meta = _frontmatter(_pack(tmp_path, vault, root, task_class="repo-review"))

    assert meta["source_commit"] == _git(repo, "rev-parse", "HEAD")
    assert meta["source_state"] == "clean"
    assert meta["contract_version"] == "1.2.0"
    assert meta["vault_commit"] == _git(vault, "rev-parse", "HEAD")
    assert meta["task_class"] == "repo-review"


def test_what_could_not_be_observed_is_left_out(tmp_path):
    # No git, no contract, no task class: nothing is recorded rather than a guess.
    vault = tmp_path / "mqobsidian"
    (vault / "memory" / "context-cards").mkdir(parents=True)
    (vault / ".mq").mkdir()
    (vault / ".mq" / "context-selection-vocabulary.json").write_text(json.dumps(VOCABULARY))
    (tmp_path / "repos" / "mq-mcp").mkdir(parents=True)

    meta = _frontmatter(_pack(tmp_path, vault, tmp_path / "repos"))

    for key in ("source_commit", "source_state", "contract_version", "vault_commit", "task_class"):
        assert key not in meta


def test_an_unchanged_repo_and_vault_is_fresh(tmp_path):
    vault, root, _ = _setup(tmp_path)
    path = _pack(tmp_path, vault, root)

    result = check_task_pack(path, vault=vault, repos_root=root)

    assert result["status"] == "FRESH", result["reasons"]
    assert result["reasons"] == []


def test_a_new_repo_commit_makes_the_pack_stale(tmp_path):
    vault, root, repo = _setup(tmp_path)
    path = _pack(tmp_path, vault, root)
    _commit(repo, "x.py", "x = 1\n")

    result = check_task_pack(path, vault=vault, repos_root=root)

    assert result["status"] == "STALE"
    assert any("mq-mcp" in r and "commit" in r for r in result["reasons"])


def test_a_new_vault_commit_makes_the_pack_stale(tmp_path):
    vault, root, _ = _setup(tmp_path)
    path = _pack(tmp_path, vault, root)
    _commit(vault, "note.md", "new\n")

    result = check_task_pack(path, vault=vault, repos_root=root)

    assert result["status"] == "STALE"
    assert any("vault" in r for r in result["reasons"])


def test_a_changed_contract_version_is_named(tmp_path):
    vault, root, repo = _setup(tmp_path)
    path = _pack(tmp_path, vault, root)
    _commit(repo, ".mq/repo-contract.json", json.dumps({"repo": "mq-mcp", "version": "1.3.0"}))

    reasons = check_task_pack(path, vault=vault, repos_root=root)["reasons"]

    assert any("1.2.0" in r and "1.3.0" in r for r in reasons)


def test_a_different_task_class_makes_the_pack_stale(tmp_path):
    vault, root, _ = _setup(tmp_path)
    path = _pack(tmp_path, vault, root, task_class="repo-review")

    result = check_task_pack(path, task_class="docs-review", vault=vault, repos_root=root)

    assert result["status"] == "STALE"
    assert any("repo-review" in r and "docs-review" in r for r in result["reasons"])


def test_uncommitted_changes_cannot_be_proven_fresh(tmp_path):
    vault, root, repo = _setup(tmp_path)
    path = _pack(tmp_path, vault, root)
    (repo / "wip.py").write_text("x = 2\n", encoding="utf-8")

    result = check_task_pack(path, vault=vault, repos_root=root)

    assert result["status"] == "UNKNOWN"
    assert any("uncommitted" in r for r in result["reasons"])


def test_a_pack_built_from_a_dirty_tree_cannot_be_proven_fresh(tmp_path):
    vault, root, repo = _setup(tmp_path)
    (repo / "wip.py").write_text("x = 2\n", encoding="utf-8")
    path = _pack(tmp_path, vault, root)
    assert _frontmatter(path)["source_state"] == "dirty"

    assert check_task_pack(path, vault=vault, repos_root=root)["status"] == "UNKNOWN"


def test_a_pack_without_provenance_is_unknown_not_fresh(tmp_path):
    vault, root, _ = _setup(tmp_path)
    path = tmp_path / "old-pack.md"
    path.write_text(
        "---\nschema: context-pack.v1\ntarget: both\ntask: t\n"
        "generated_at: 2026-06-16T00:00:00Z\nrepo: mq-mcp\nsummary: s\n---\n",
        encoding="utf-8",
    )

    result = check_task_pack(path, vault=vault, repos_root=root)

    assert result["status"] == "UNKNOWN"


def test_stale_wins_over_unknown(tmp_path):
    vault, root, repo = _setup(tmp_path)
    path = _pack(tmp_path, vault, root)
    _commit(repo, "x.py", "x = 1\n")
    (repo / "wip.py").write_text("x = 2\n", encoding="utf-8")

    assert check_task_pack(path, vault=vault, repos_root=root)["status"] == "STALE"


def _cli_check(path: Path, vault: Path, root: Path, *extra: str):
    return runner.invoke(
        app,
        ["context", "check", str(path), "--vault", str(vault), "--repos-root", str(root),
         "--json", *extra],
    )


def test_cli_check_exit_codes_follow_the_status(tmp_path):
    vault, root, repo = _setup(tmp_path)
    path = _pack(tmp_path, vault, root)

    fresh = _cli_check(path, vault, root)
    assert fresh.exit_code == 0, fresh.output
    assert json.loads(fresh.stdout)["status"] == "FRESH"

    (repo / "wip.py").write_text("x = 2\n", encoding="utf-8")
    assert _cli_check(path, vault, root).exit_code == 3

    _commit(repo, "wip.py", "x = 2\n")
    assert _cli_check(path, vault, root).exit_code == 1


def test_cli_check_rejects_a_file_that_is_not_a_pack(tmp_path):
    vault, root, _ = _setup(tmp_path)
    path = tmp_path / "notes.md"
    path.write_text("# notes\n", encoding="utf-8")

    assert _cli_check(path, vault, root).exit_code == 2


def test_cli_pack_stamps_an_explicit_task_class_only(tmp_path):
    vault, root, _ = _setup(tmp_path)
    out = tmp_path / "pack.md"
    base = ["context", "pack", "update docs", "--repo", "mq-mcp", "--vault", str(vault),
            "--repos-root", str(root), "--output", str(out)]

    assert runner.invoke(app, base).exit_code == 0
    assert "task_class" not in _frontmatter(out)

    assert runner.invoke(app, [*base, "--task-class", "docs-review"]).exit_code == 0
    assert _frontmatter(out)["task_class"] == "docs-review"


def test_a_stamped_pack_conforms_to_the_vendored_schema(tmp_path):
    from jsonschema import Draft202012Validator

    vault, root, _ = _setup(tmp_path)
    meta = _frontmatter(_pack(tmp_path, vault, root, task_class="repo-review"))
    assert "source_commit" in meta

    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "context_pack.schema.json"
    validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))
    errors = [e.message for e in validator.iter_errors(meta)]
    assert not errors, errors
