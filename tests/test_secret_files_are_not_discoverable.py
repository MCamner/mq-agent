"""A secret a review can quote is a secret a review can publish.

Found in real use, not by a test: `docs-audit` listed the repository root, a
later step fanned out over the result, and `.env` was first in the list. Its
contents became part of the material the routed docs-review reads and cites.
Nothing left the machine that time — the model is local and the review happened
not to quote it. That is luck and topology, not a control.
"""
from __future__ import annotations

from pathlib import Path

from mq_agent.core.executor import Executor
from mq_agent.core.safety import SafetyGate, SafetyMode
from mq_agent.core.state import AgentState, PlanStep, StepStatus
from mq_agent.tools.repo_tools import _is_secret, find_files, list_files, read_file


def _repo(tmp_path: Path) -> Path:
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-real-secret\n")
    (tmp_path / ".env.local").write_text("TOKEN=also-secret\n")
    (tmp_path / ".env.example").write_text("OPENAI_API_KEY=\n")
    (tmp_path / "server.pem").write_text("-----BEGIN PRIVATE KEY-----\n")
    (tmp_path / "id_rsa").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n")
    (tmp_path / "README.md").write_text("# Docs\n")
    return tmp_path


def test_discovery_does_not_offer_a_secret(tmp_path) -> None:
    listed = list_files(str(_repo(tmp_path))).splitlines()

    assert not [name for name in listed if Path(name).name == ".env"]
    assert not [name for name in listed if Path(name).name == ".env.local"]
    assert not [name for name in listed if Path(name).name == "server.pem"]
    assert not [name for name in listed if Path(name).name == "id_rsa"]


def test_a_documented_example_is_still_documentation(tmp_path) -> None:
    # A docs audit that cannot see .env.example is worse off, and the file
    # exists precisely because it holds no secret.
    listed = list_files(str(_repo(tmp_path))).splitlines()

    assert [name for name in listed if Path(name).name == ".env.example"]
    assert [name for name in listed if Path(name).name == "README.md"]


def test_a_recursive_search_does_not_offer_a_secret_either(tmp_path) -> None:
    nested = _repo(tmp_path) / "config"
    nested.mkdir()
    (nested / ".env").write_text("NESTED=secret\n")

    found = find_files(str(tmp_path), "*").splitlines()

    assert not [name for name in found if Path(name).name == ".env"]


def test_the_fan_out_that_caused_this_cannot_reach_a_secret(tmp_path) -> None:
    """The exact chain from the real run, held down end to end.

    list the repository → read each file found → material for the review.
    """
    repo = _repo(tmp_path)
    find = PlanStep(index=0, description="list", tool="list_files", args={"path": str(repo)})
    read = PlanStep(index=1, description="read", tool="read_file", for_each={"step": 0, "as": "path"})
    state = AgentState(goal="audit")
    state.plan = [find, read]

    executor = Executor(
        SafetyGate(SafetyMode.READ_ONLY),
        {"list_files": list_files, "read_file": read_file},
    )
    executor.run_step(find, state)
    executor.run_step(read, state)

    assert read.status is StepStatus.SUCCESS
    assert "sk-real-secret" not in str(read.result)
    assert "BEGIN PRIVATE KEY" not in str(read.result)
    assert "# Docs" in str(read.result)


def test_what_counts_as_a_secret_name() -> None:
    for name in (".env", ".env.local", ".env.production", "id_rsa", "server.pem",
                 "app.key", "store.p12", ".netrc", "credentials"):
        assert _is_secret(name), name
    for name in (".env.example", ".env.sample", ".env.template", ".env.dist",
                 "README.md", "keys.md", "environment.py"):
        assert not _is_secret(name), name


def test_a_step_that_names_a_secret_outright_is_not_blocked_here(tmp_path) -> None:
    """The residual, stated rather than implied.

    This fix removes the path by which a secret reached the material — being
    offered by discovery and read by a fan-out. A step that names `.env`
    directly still reads it, because `read_file` is a general tool and blocking
    it there would break the legitimate case of being asked to read one.
    """
    secret = _repo(tmp_path) / ".env"

    assert "sk-real-secret" in read_file(str(secret))
