"""One reading of MQ_MCP_DIR, and the two questions consumers ask of it.

`MQ_MCP_DIR` has always been allowed in two shapes — the repo root
(`~/mq-mcp`) and the Python project inside it (`~/mq-mcp/mq-mcp`) — and four
modules grew their own reading of it, each with a different marker and a
different answer:

    runtime_identity.mq_mcp_root   probes .git        → repo root
    mcp.manager.mq_mcp_dir         probes server.py   → project dir
    memory.cochange_observation    no probe, appends "/mq-mcp"
    tools.model_runtime            no probe, assumes the repo root

Two of those were already wrong on a machine configured the other way. The
manager one started `uv run mcp run server.py` where there is no server.py and
the child exited rc=1; the model_runtime one looks for `models/` under the
project directory and reports "drift not checked" when it is not there.

So the consolidation cannot be "one resolver returning one path". Repo root and
project directory are different questions with different correct answers, and
what has to be shared is the *reading* of the variable — normalise once, probe
once, answer both. This file states that contract.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mq_agent.core import mq_mcp_layout as layout


# ── fixtures ────────────────────────────────────────────────────────────────

def _checkout(tmp_path: Path) -> tuple[Path, Path]:
    """Build mq-mcp's real shape: markers at the root, markers in the project."""
    root = tmp_path / "mq-mcp"
    project = root / "mq-mcp"
    project.mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "models" / "ollama").mkdir(parents=True)
    (project / "server.py").write_text("x = 1\n", encoding="utf-8")
    (project / "bridge.py").write_text("x = 1\n", encoding="utf-8")
    (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    return root, project


# ── both allowed shapes give the same two answers ───────────────────────────

@pytest.mark.parametrize("shape", ["repo-root", "project-dir"])
def test_both_allowed_shapes_resolve_to_the_same_layout(tmp_path, monkeypatch, shape):
    """The variable may name either directory. Neither reading may lose one."""
    root, project = _checkout(tmp_path)
    monkeypatch.setenv("MQ_MCP_DIR", str(root if shape == "repo-root" else project))

    resolved = layout.mq_mcp_layout()

    assert resolved.root == root
    assert resolved.project == project


def test_the_two_answers_can_never_describe_different_checkouts(tmp_path, monkeypatch):
    """The invariant the split resolvers could not offer.

    Reading the variable twice in two modules allowed root and project to come
    from different trees. Reading it once cannot.
    """
    root, project = _checkout(tmp_path)
    monkeypatch.setenv("MQ_MCP_DIR", str(project))

    resolved = layout.mq_mcp_layout()

    assert resolved.project is not None and resolved.root is not None
    assert resolved.project.parent == resolved.root


def test_the_default_is_the_home_checkout(tmp_path, monkeypatch):
    """No variable is not a reason to guess from cwd."""
    root, project = _checkout(tmp_path)
    monkeypatch.delenv("MQ_MCP_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    resolved = layout.mq_mcp_layout()

    assert resolved.root == root
    assert resolved.project == project


def test_an_explicit_argument_outranks_the_environment(tmp_path, monkeypatch):
    """The injectable seam co-change already had, kept and made uniform."""
    root, project = _checkout(tmp_path)
    monkeypatch.setenv("MQ_MCP_DIR", str(tmp_path / "somewhere-else"))

    resolved = layout.mq_mcp_layout(root)

    assert resolved.project == project


# ── absence is reported, not invented ───────────────────────────────────────

def test_a_directory_that_is_neither_shape_resolves_to_nothing(tmp_path, monkeypatch):
    """Not a refusal here — the consumer's own failure path reports it."""
    empty = tmp_path / "nothing"
    empty.mkdir()
    monkeypatch.setenv("MQ_MCP_DIR", str(empty))

    resolved = layout.mq_mcp_layout()

    assert resolved.root is None
    assert resolved.project is None
    assert resolved.configured == empty


def test_a_checkout_without_the_project_still_reports_the_root(tmp_path, monkeypatch):
    """Half an answer is an answer. Inventing the other half is not."""
    root = tmp_path / "mq-mcp"
    root.mkdir()
    (root / ".git").mkdir()
    monkeypatch.setenv("MQ_MCP_DIR", str(root))

    resolved = layout.mq_mcp_layout()

    assert resolved.root == root
    assert resolved.project is None


def test_a_project_outside_a_checkout_still_reports_the_project(tmp_path, monkeypatch):
    """A wheel or a copied tree has no .git. That is not a broken project."""
    project = tmp_path / "mq-mcp"
    project.mkdir()
    (project / "server.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setenv("MQ_MCP_DIR", str(project))

    resolved = layout.mq_mcp_layout()

    assert resolved.project == project
    assert resolved.root is None


def test_the_cwd_is_never_consulted(tmp_path, monkeypatch):
    """Standing inside an mq-mcp checkout must not change the answer."""
    root, _ = _checkout(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("MQ_MCP_DIR", str(elsewhere))
    monkeypatch.chdir(root)

    resolved = layout.mq_mcp_layout()

    assert resolved.root is None
    assert resolved.project is None


def test_resolution_starts_nothing(tmp_path, monkeypatch):
    """A lookup is a lookup. Processes belong to the consumers."""
    root, _ = _checkout(tmp_path)
    monkeypatch.setenv("MQ_MCP_DIR", str(root))

    def _forbidden(*args, **kwargs):
        raise AssertionError("mq_mcp_layout must not execute anything")

    monkeypatch.setattr(subprocess, "run", _forbidden)
    monkeypatch.setattr(subprocess, "Popen", _forbidden)

    layout.mq_mcp_layout()


# ── the run-from directory consumers actually need ──────────────────────────

def test_the_run_directory_is_the_project_when_one_resolves(tmp_path, monkeypatch):
    root, project = _checkout(tmp_path)
    monkeypatch.setenv("MQ_MCP_DIR", str(root))

    assert layout.mq_mcp_run_dir() == project


def test_the_run_directory_falls_back_to_what_was_configured(tmp_path, monkeypatch):
    """So a misconfiguration surfaces where it is legible.

    `manager.start()` reports a missing directory and `run_cochange` returns
    None on the subprocess error. Both are better than this raising inside an
    unrelated call, and both name the path the operator actually set.
    """
    empty = tmp_path / "nothing"
    empty.mkdir()
    monkeypatch.setenv("MQ_MCP_DIR", str(empty))

    assert layout.mq_mcp_run_dir() == empty


# ── every consumer reads it through here ────────────────────────────────────

def test_the_manager_runs_the_child_where_server_py_is(tmp_path, monkeypatch):
    from mq_agent.mcp import manager

    root, project = _checkout(tmp_path)
    monkeypatch.setenv("MQ_MCP_DIR", str(root))

    assert manager.mq_mcp_dir() == project
    assert (manager.mq_mcp_dir() / "server.py").exists()


def test_runtime_identity_reads_the_checkout_from_either_shape(tmp_path, monkeypatch):
    from mq_agent.core import runtime_identity

    root, project = _checkout(tmp_path)
    monkeypatch.setenv("MQ_MCP_DIR", str(project))

    assert runtime_identity.mq_mcp_root() == root


def test_the_modelfile_is_looked_for_under_the_checkout(tmp_path, monkeypatch):
    """The live defect this consolidation closes.

    `models/` lives at the repo root. Read as the project directory, the path
    becomes `<root>/mq-mcp/models/...`, which does not exist, and the drift
    check reports "not found" instead of comparing anything — silently, because
    its failure mode is WARN rather than an error.
    """
    from mq_agent.tools import model_runtime

    root, project = _checkout(tmp_path)
    expected = root / "models" / "ollama" / "Modelfile.mq-learn"
    expected.write_text("FROM x\n", encoding="utf-8")
    monkeypatch.setenv("MQ_MCP_DIR", str(project))

    assert model_runtime._mq_learn_modelfile_path() == expected
    assert model_runtime._mq_learn_modelfile_path().exists()


def test_the_cochange_bridge_runs_where_bridge_py_is(tmp_path, monkeypatch):
    """Bridget is spawned with `uv --directory`, so the directory must be right."""
    from mq_agent.memory import cochange_observation as co

    root, project = _checkout(tmp_path)
    monkeypatch.setenv("MQ_MCP_DIR", str(root))
    captured: dict = {}

    class _Result:
        returncode = 1
        stdout = ""
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(co.subprocess, "run", _fake_run)
    co.run_cochange(tmp_path, "a.py")

    cmd = captured["cmd"]
    assert cmd[cmd.index("--directory") + 1] == str(project)


# ── the guard against a fifth reader ────────────────────────────────────────

def test_only_one_module_reads_the_variable():
    """What "consolidated" has to mean to stay true.

    Four readings drifted apart because nothing stopped a fifth from being
    added. This fails when one is, and names the line.

    It matches an environment lookup naming the variable, not the variable's
    name on its own — a module that explains why it no longer reads it should
    be able to say so. A reader that hides the name behind a constant defeats
    this; that is a deliberate bypass, not the accident being guarded against.
    """
    package = Path(layout.__file__).resolve().parents[1]
    canonical = Path(layout.__file__).resolve()

    readers = []
    for source in sorted(package.rglob("*.py")):
        if source.resolve() == canonical:
            continue
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            if "MQ_MCP_DIR" in line and ("environ" in line or "getenv" in line):
                readers.append(f"{source.relative_to(package.parent).as_posix()}:{number}")

    assert readers == [], (
        "MQ_MCP_DIR must be read only by mq_agent/core/mq_mcp_layout.py; "
        f"also read at: {readers}"
    )
