"""Tests for the local, provider-neutral NotebookLM pack exporter."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from typer.testing import CliRunner

from mq_agent.main import app
from mq_agent.tools.context_export import default_vault
from mq_agent.tools.notebook_export import build_notebook_pack

runner = CliRunner()

# mqobsidian owns notebook-pack.v1. A byte copy lives here so every test
# below validates against the real contract instead of a hand-written stub
# that cannot drift-check; test_vendored_schema_matches_mqobsidian keeps the
# copy honest.
VENDORED_SCHEMA = Path(__file__).parent / "fixtures" / "notebook-pack.v1.json"


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "mqobsidian"
    (vault / ".mq").mkdir(parents=True)
    (vault / "schemas").mkdir()
    (vault / "docs" / "decision-records").mkdir(parents=True)
    (vault / "docs" / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (vault / "docs" / "decision-records" / "DEC-001.md").write_text(
        "# Decision\n", encoding="utf-8"
    )
    (vault / ".mq" / "notebooks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "provider": "notebooklm",
                "status": "experimental",
                "role": "consumer",
                "write_back": False,
                "output_root": ".notebooklm",
                "notebooks": {
                    "mq-stack-intelligence": {
                        "display_name": "MQ Stack Intelligence",
                        "purpose": "Test synthesis",
                        "classification": "public-safe",
                        "source_lanes": {
                            "reviewed": {"provider": "mqobsidian", "status": "active"},
                            "observed": {
                                "provider": "codegraph",
                                "status": "deferred",
                                "requires_revision": True,
                            },
                        },
                        "include": [
                            "docs/architecture.md",
                            "docs/decision-records/*.md",
                        ],
                        "exclude": [".notebooklm/**"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (vault / "schemas" / "notebook-pack.v1.json").write_bytes(
        VENDORED_SCHEMA.read_bytes()
    )
    return vault


def _git_vault(tmp_path: Path) -> Path:
    """A vault that is a real git repo with one committed and one dirty source."""
    vault = _vault(tmp_path)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    for args in (
        ["init", "-q"],
        ["add", "-A"],
        ["commit", "-qm", "seed"],
    ):
        subprocess.run(["git", "-C", str(vault), *args], check=True, env=env)
    # Dirty exactly one selected source after the commit.
    (vault / "docs" / "architecture.md").write_text(
        "# Architecture\n\nuncommitted edit\n", encoding="utf-8"
    )
    return vault


def test_dirty_sources_are_flagged_against_their_commit(tmp_path):
    vault = _git_vault(tmp_path)
    report = build_notebook_pack("mq-stack-intelligence", vault=vault)

    revisions = {
        source["path"]: source["revision"] for source in report["manifest"]["sources"]
    }
    assert revisions["docs/architecture.md"]["dirty"] is True
    assert revisions["docs/decision-records/DEC-001.md"]["dirty"] is False
    assert len({rev["commit"] for rev in revisions.values()}) == 1


def test_clean_vault_reports_no_dirty_sources(tmp_path):
    vault = _git_vault(tmp_path)
    (vault / "docs" / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    report = build_notebook_pack("mq-stack-intelligence", vault=vault)

    assert all(
        source["revision"]["dirty"] is False
        for source in report["manifest"]["sources"]
    )


def test_non_git_vault_omits_revision_rather_than_guessing(tmp_path):
    vault = _vault(tmp_path)
    report = build_notebook_pack("mq-stack-intelligence", vault=vault)

    assert all("revision" not in s for s in report["manifest"]["sources"])


def test_preview_is_read_only_and_selects_reviewed_markdown(tmp_path):
    vault = _vault(tmp_path)
    report = build_notebook_pack("mq-stack-intelligence", vault=vault)

    assert report["dry_run"] is True
    assert report["source_count"] == 2
    assert report["would_write"]
    assert not (vault / ".notebooklm").exists()
    assert report["manifest"]["notebook"]["id"] == "mq-stack-intelligence"
    assert all(source["classification"] == "public-safe" for source in report["manifest"]["sources"])


def test_write_preserves_source_paths_and_is_deterministic(tmp_path):
    vault = _vault(tmp_path)
    first = build_notebook_pack("mq-stack-intelligence", vault=vault, write=True)
    second = build_notebook_pack("mq-stack-intelligence", vault=vault)

    pack = vault / ".notebooklm" / "mq-stack-intelligence"
    assert (pack / "manifest.json").is_file()
    assert (pack / "sources" / "docs" / "architecture.md").is_file()
    assert first["content_hash"] == second["content_hash"]
    assert len(first["content_hash"]) == 64


def test_unsafe_or_overbroad_include_is_rejected(tmp_path):
    vault = _vault(tmp_path)
    profile_path = vault / ".mq" / "notebooks.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    for unsafe in ("../private.md", "/private.md", "systems/**"):
        profile["notebooks"]["mq-stack-intelligence"]["include"] = [unsafe]
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        try:
            build_notebook_pack("mq-stack-intelligence", vault=vault)
        except ValueError as exc:
            assert "unsafe" in str(exc) or "too broad" in str(exc)
        else:
            raise AssertionError(f"unsafe include accepted: {unsafe}")


def test_cli_defaults_to_preview_and_requires_write_flag(tmp_path):
    vault = _vault(tmp_path)
    result = runner.invoke(
        app,
        ["notebook", "pack", "mq-stack-intelligence", "--vault", str(vault), "--json"],
    )

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["dry_run"] is True
    assert report["source_count"] == 2
    assert not (vault / ".notebooklm").exists()


def test_report_surfaces_dirty_count_for_the_operator(tmp_path):
    vault = _git_vault(tmp_path)
    report = build_notebook_pack("mq-stack-intelligence", vault=vault)

    assert report["dirty_source_count"] == 1
    assert report["dirty_sources"] == ["docs/architecture.md"]


def test_cli_preview_warns_when_sources_are_dirty(tmp_path):
    vault = _git_vault(tmp_path)
    result = runner.invoke(
        app, ["notebook", "pack", "mq-stack-intelligence", "--vault", str(vault)]
    )

    assert result.exit_code == 0
    assert "1" in result.stdout
    assert "dirty" in result.stdout.lower()


def test_vendored_schema_matches_mqobsidian():
    """The vendored contract must not drift from the vault that owns it.

    Skips only when no local vault is reachable (CI, a fresh clone). mqobsidian
    DEC-003 warns about exactly this shape: a schema test that skipped itself
    whenever the library was missing — which was always, in CI — leaving the one
    real check structurally silent. The difference here is deliberate: the
    vendored copy is the schema every other test in this file validates against,
    so contract validation never goes silent; only the drift comparison does.
    Closing that remaining gap is mqobsidian roadmap 12f.
    """
    vault = default_vault()
    owner = vault / "schemas" / "notebook-pack.v1.json"
    if not owner.is_file():
        pytest.skip(f"no mqobsidian schema at {owner}; set MQ_OBSIDIAN_DIR to drift-check")

    assert json.loads(VENDORED_SCHEMA.read_text(encoding="utf-8")) == json.loads(
        owner.read_text(encoding="utf-8")
    ), (
        "tests/fixtures/notebook-pack.v1.json is out of date with mqobsidian — "
        f"copy {owner} over it and re-run"
    )
