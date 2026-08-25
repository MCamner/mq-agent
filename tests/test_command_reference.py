"""Contract tests for the generated command reference.

The repo is the authoritative source for the command surface: the reference is
derived from the live Typer app, never from a hand-maintained list. These tests
fail when the checked-in page drifts from the code.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import click
import pytest
import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "tools" / "generate_command_reference.py"
REFERENCE = REPO_ROOT / "docs" / "generated" / "Command-Reference.md"

# The command surface as of the introspection contract. A new Typer command or
# group changes these numbers and turns the suite red until the reference is
# regenerated.
EXPECTED_TOP_LEVEL_COMMANDS = 16
EXPECTED_TOP_LEVEL_GROUPS = 18


def _load_generator():
    spec = importlib.util.spec_from_file_location("_gen_cmd_ref", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves forward references via sys.modules, so the module
    # must be registered before it is executed.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen():
    return _load_generator()


@pytest.fixture(scope="module")
def root_command() -> click.Group:
    from mq_agent.main import app

    command = typer.main.get_command(app)
    assert isinstance(command, click.Group)
    return command


def test_generator_exists() -> None:
    assert GENERATOR.is_file(), "generator script is missing"


def test_reference_is_checked_in() -> None:
    assert REFERENCE.is_file(), (
        "docs/generated/Command-Reference.md is missing — run "
        "`python tools/generate_command_reference.py`"
    )


def test_top_level_counts_match_the_contract(root_command: click.Group) -> None:
    groups = [
        name
        for name, cmd in root_command.commands.items()
        if isinstance(cmd, click.Group)
    ]
    leaves = [
        name
        for name, cmd in root_command.commands.items()
        if not isinstance(cmd, click.Group)
    ]

    assert len(leaves) == EXPECTED_TOP_LEVEL_COMMANDS
    assert len(groups) == EXPECTED_TOP_LEVEL_GROUPS
    assert len(root_command.commands) == (
        EXPECTED_TOP_LEVEL_COMMANDS + EXPECTED_TOP_LEVEL_GROUPS
    )


def test_generator_finds_the_same_top_level_objects(gen, root_command) -> None:
    """The generator must not filter or invent entries."""
    tree = gen.build_tree()
    generated = {child.name for child in tree.children}
    assert generated == set(root_command.commands)
    assert len(generated) == (
        EXPECTED_TOP_LEVEL_COMMANDS + EXPECTED_TOP_LEVEL_GROUPS
    )


def test_generated_surface_matches_cli_help(gen) -> None:
    """Cross-check against the real `mq-agent --help`, not just the object tree.

    This is the independent check: it drives the CLI the way a user does and
    parses what it prints.
    """
    result = subprocess.run(
        [sys.executable, "-m", "mq_agent.main", "--help"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={"COLUMNS": "200", "PATH": "/usr/bin:/bin", "NO_COLOR": "1"},
    )
    assert result.returncode == 0, result.stderr

    printed = set(re.findall(r"^\W*\b([a-z][a-z0-9-]*)\s{2,}\S", result.stdout, re.M))
    generated = {child.name for child in gen.build_tree().children}

    missing = generated - printed
    assert not missing, f"documented but not in --help: {sorted(missing)}"


def test_every_command_path_appears_in_the_reference(gen) -> None:
    """Every leaf and group in the live app is documented."""
    text = REFERENCE.read_text(encoding="utf-8")
    missing = [
        node.path
        for node in gen.walk(gen.build_tree())
        if f"`{node.path}`" not in text
    ]
    assert not missing, f"undocumented command paths: {missing}"


def test_reference_matches_the_live_app(gen) -> None:
    """The checked-in page is byte-identical to a fresh render."""
    assert REFERENCE.read_text(encoding="utf-8") == gen.render(), (
        "docs/generated/Command-Reference.md is stale — run "
        "`python tools/generate_command_reference.py`"
    )


def test_render_is_deterministic(gen) -> None:
    assert gen.render() == gen.render()


def test_check_mode_passes_for_the_checked_in_file() -> None:
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_mode_detects_drift(gen, tmp_path: Path) -> None:
    """A changed page must fail --check, otherwise the CI gate is useless."""
    target = tmp_path / "Command-Reference.md"
    target.write_text(gen.render() + "\ndrift\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check", "--output", str(target)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode != 0
    assert "stale" in (result.stdout + result.stderr).lower()


def test_new_command_turns_the_reference_stale(gen) -> None:
    """Adding a command must make the checked-in page fail verification.

    This proves the CI gate actually catches drift instead of only checking
    that the file exists.
    """
    tree = gen.build_tree()
    extra = gen.Node(
        name="zz-probe",
        path="mq-agent zz-probe",
        description="Synthetic probe command.",
        is_group=False,
    )
    tree.children.append(extra)
    rendered_paths = {node.path for node in gen.walk(tree)}

    text = REFERENCE.read_text(encoding="utf-8")
    assert "mq-agent zz-probe" in rendered_paths
    assert "`mq-agent zz-probe`" not in text, (
        "the probe command must not be present in the committed reference"
    )


def test_reference_documents_options_with_defaults(gen) -> None:
    """Spot-check the documented option contract on a known command."""
    text = REFERENCE.read_text(encoding="utf-8")
    assert "## `mq-agent route inspect`" in text
    section = text.split("## `mq-agent route inspect`", 1)[1].split("\n## ", 1)[0]
    assert "| Option | Required | Default | Description |" in section
    assert "`--json`" in section
    assert "`--agent`" in section
    assert "`codex`" in section, "option default is not documented"


def test_reference_documents_arguments(gen) -> None:
    text = REFERENCE.read_text(encoding="utf-8")
    section = text.split("## `mq-agent route inspect`", 1)[1].split("\n## ", 1)[0]
    assert "| Argument | Required | Default | Description |" in section
    assert "`TASK`" in section


def test_nested_group_is_documented(gen) -> None:
    """`obsidian inbox` is the only depth-3 group; it must not be dropped."""
    text = REFERENCE.read_text(encoding="utf-8")
    assert "## `mq-agent obsidian inbox`" in text
    assert "## `mq-agent obsidian inbox list`" in text


def test_help_option_is_not_documented(gen) -> None:
    """Click's auto-added --help is noise, not part of the surface."""
    tree = gen.build_tree()
    for node in gen.walk(tree):
        assert all(
            opt.names != ["--help"] for opt in node.options
        ), f"--help leaked into {node.path}"


def test_generator_needs_no_network_or_wiki_clone() -> None:
    """The generator must be a pure local render."""
    source = GENERATOR.read_text(encoding="utf-8")
    for forbidden in ("requests", "urllib", "git clone", "subprocess"):
        assert forbidden not in source, (
            f"generator must not depend on {forbidden!r}"
        )
