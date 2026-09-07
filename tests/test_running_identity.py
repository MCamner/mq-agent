"""mq-agent asks a live component what it is, and believes only what it hears.

Phase 4b is the consumer half. The producer was the hard part; this side must
add no identity logic of its own. It asks, validates the answer against the
canonical contract, and hands the result to the reducer that already exists.

The failure modes it must not have are all the same shape: turning an absence
into a claim. Nothing listening is not a mismatch. A refused connection is not
an unknown identity. A malformed answer is not silence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from mq_agent.core import runtime_identity, stack_provenance


def _identity(**overrides: Any) -> dict[str, Any]:
    record = {
        "schema": "mq.runtime-identity.v1",
        "component": "mq-mcp",
        "version": "2.0.2",
        "commit": "a" * 40,
        "install_type": "unknown",
        "identity_quality": "verified",
    }
    record.update(overrides)
    return record


class _Response:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        if isinstance(self._payload, str):
            raise ValueError("not json")
        return self._payload


@pytest.fixture
def answers(monkeypatch):
    """Make the local bridge say something, without running one."""

    def _install(payload: Any, status_code: int = 200) -> None:
        import httpx

        monkeypatch.setattr(
            httpx, "get", lambda *a, **k: _Response(payload, status_code)
        )

    return _install


@pytest.fixture
def refuses(monkeypatch):
    """Make the local bridge refuse, as nothing listening would."""
    import httpx

    def _refuse(*_args, **_kwargs):
        raise httpx.ConnectError("nothing is listening")

    monkeypatch.setattr(httpx, "get", _refuse)


# --- asking, and saying that you asked ------------------------------------


def test_a_component_that_answers_is_reported_as_running(answers):
    answers(_identity())

    running, probe = runtime_identity.probe_running(runtime_identity.mq_mcp_endpoint())

    assert running == _identity()
    assert probe["attempted"] is True
    assert probe["reachable"] is True
    assert probe["endpoint"].endswith("/runtime-identity")


def test_nothing_listening_is_recorded_as_asked_and_absent(refuses):
    """The control case. A stopped server is a fact, not a fault."""
    running, probe = runtime_identity.probe_running(runtime_identity.mq_mcp_endpoint())

    assert running is None
    assert probe["attempted"] is True
    assert probe["reachable"] is False


def test_asking_never_raises(monkeypatch):
    """Provenance observes. It does not fail a run by looking."""
    import httpx

    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    running, probe = runtime_identity.probe_running("http://127.0.0.1:1/x")

    assert running is None
    assert probe["reachable"] is False


def test_the_endpoint_follows_the_variables_mq_mcp_itself_reads(monkeypatch):
    monkeypatch.setenv("MQ_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("MQ_MCP_PORT", "9999")

    assert runtime_identity.mq_mcp_endpoint() == "http://127.0.0.1:9999/runtime-identity"


# --- an absence is never a claim ------------------------------------------


def test_a_stopped_component_produces_no_finding_at_all(refuses, monkeypatch, tmp_path):
    """Atlas's control case, end to end: no process, no accusations."""
    monkeypatch.setattr(runtime_identity, "mq_mcp_root", lambda: None)

    component = stack_provenance.observe_mq_mcp()

    assert component is None, "a component with nothing to say is absent, not empty"


def test_a_stopped_component_with_a_checkout_still_accuses_nothing(
    refuses, monkeypatch, tmp_path
):
    root = _repository(tmp_path)
    monkeypatch.setattr(runtime_identity, "mq_mcp_root", lambda: root)

    observed = stack_provenance.observe_mq_mcp()
    assert observed is not None
    assessed = stack_provenance.assess(observed)

    assert assessed["running"] is None
    assert assessed["comparison"]["running_matches_checkout"] is None
    assert assessed["comparison"]["running_matches_installed"] is None
    for invented in (
        "RTP008_RUNNING_IDENTITY_UNKNOWN",
        "RTP009_RUNNING_INSTALLED_MISMATCH",
        "RTP010_RUNNING_CHECKOUT_MISMATCH",
    ):
        assert invented not in assessed["reasons"]


def test_mq_agent_never_reads_mq_mcp_s_installed_distribution(refuses, monkeypatch, tmp_path):
    """This process can read its own distribution metadata, not another's."""
    root = _repository(tmp_path)
    monkeypatch.setattr(runtime_identity, "mq_mcp_root", lambda: root)

    component = stack_provenance.observe_mq_mcp()

    assert component is not None
    assert component["installed"] is None


# --- what the component says is checked, not trusted ----------------------


def test_a_malformed_answer_fails_rather_than_going_quiet(answers, monkeypatch, tmp_path):
    answers({"banana": 42})
    monkeypatch.setattr(runtime_identity, "mq_mcp_root", lambda: None)

    observed = stack_provenance.observe_mq_mcp()
    assert observed is not None
    assessed = stack_provenance.assess(observed)

    assert "RTP013_RUNTIME_IDENTITY_INVALID" in assessed["reasons"]
    assert assessed["status"] == "FAIL"


def test_an_answer_that_is_not_a_record_at_all_is_still_a_finding(
    answers, monkeypatch, tmp_path
):
    """Something answered on the bridge and said something else entirely."""
    answers("<html>not me</html>")
    monkeypatch.setattr(runtime_identity, "mq_mcp_root", lambda: None)

    observed = stack_provenance.observe_mq_mcp()
    assert observed is not None
    assessed = stack_provenance.assess(observed)

    assert "RTP013_RUNTIME_IDENTITY_INVALID" in assessed["reasons"]


def test_a_component_that_cannot_identify_itself_is_unavailable_not_wrong(
    answers, monkeypatch, tmp_path
):
    answers(
        _identity(version=None, commit=None, identity_quality="unknown")
    )
    monkeypatch.setattr(runtime_identity, "mq_mcp_root", lambda: None)

    observed = stack_provenance.observe_mq_mcp()
    assert observed is not None
    assessed = stack_provenance.assess(observed)

    assert "RTP008_RUNNING_IDENTITY_UNKNOWN" in assessed["reasons"]
    assert assessed["status"] == "UNAVAILABLE"
    assert "RTP010_RUNNING_CHECKOUT_MISMATCH" not in assessed["reasons"]


def test_a_status_code_is_an_answer(answers):
    """A build from before the route existed replies 404.

    Calling that unreachable would make a live process look exactly like a
    stopped one, which is the distinction this probe exists to draw. Only a
    refused connection or a failed request means nothing answered.
    """
    answers(_identity(), status_code=404)

    running, probe = runtime_identity.probe_running(runtime_identity.mq_mcp_endpoint())

    assert probe["reachable"] is True
    assert running is None


def test_something_running_that_cannot_be_identified_is_unavailable(
    answers, monkeypatch
):
    answers(_identity(), status_code=404)
    monkeypatch.setattr(runtime_identity, "mq_mcp_root", lambda: None)

    observed = stack_provenance.observe_mq_mcp()
    assert observed is not None
    assessed = stack_provenance.assess(observed)

    assert "RTP008_RUNNING_IDENTITY_UNKNOWN" in assessed["reasons"]
    assert "RTP013_RUNTIME_IDENTITY_INVALID" not in assessed["reasons"]
    assert assessed["status"] == "UNAVAILABLE"


def test_a_refused_connection_stays_silent(refuses, monkeypatch, tmp_path):
    """The other side of the same line: nothing answered, so nothing is said."""
    monkeypatch.setattr(runtime_identity, "mq_mcp_root", lambda: _repository(tmp_path))

    observed = stack_provenance.observe_mq_mcp()
    assert observed is not None
    assessed = stack_provenance.assess(observed)

    assert assessed["running_probe"]["reachable"] is False
    assert "RTP008_RUNNING_IDENTITY_UNKNOWN" not in assessed["reasons"]


# --- a name is not a subject ----------------------------------------------


def test_an_identity_naming_another_component_contradicts_the_record(
    answers, monkeypatch
):
    """The producer's lesson, applied to the consumer.

    The contract accepts any component name, so a perfectly valid record can
    describe something else entirely. Filed under `mq-mcp`, that record makes
    the provenance record contradict itself — which is what RTP013 is for.
    """
    answers(_identity(component="something-else"))
    monkeypatch.setattr(runtime_identity, "mq_mcp_root", lambda: None)

    observed = stack_provenance.observe_mq_mcp()
    assert observed is not None
    assessed = stack_provenance.assess(observed)

    assert "RTP013_RUNTIME_IDENTITY_INVALID" in assessed["reasons"]
    assert assessed["status"] == "FAIL"


def test_an_installed_identity_must_also_name_its_own_component():
    """Both identity layers, one rule."""
    assessed = stack_provenance.assess(
        {
            "name": "mq-mcp",
            "checkout": None,
            "integration": None,
            "remote": None,
            "installed": runtime_identity.build_identity(
                component="mq-agent", version="1.28.0", commit="a" * 40,
                install_type="editable",
            ),
            "running": None,
            "running_probe": None,
            "release": None,
        }
    )

    assert "RTP013_RUNTIME_IDENTITY_INVALID" in assessed["reasons"]


def test_a_matching_name_is_not_a_finding(answers, monkeypatch):
    answers(_identity(component="mq-mcp"))
    monkeypatch.setattr(runtime_identity, "mq_mcp_root", lambda: None)

    observed = stack_provenance.observe_mq_mcp()
    assert observed is not None
    assessed = stack_provenance.assess(observed)

    assert "RTP013_RUNTIME_IDENTITY_INVALID" not in assessed["reasons"]


# --- the mismatch this whole release exists to expose ---------------------


def _repository(tmp_path: Path) -> Path:
    import subprocess

    root = tmp_path / "mq-mcp"
    root.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()

    git("init", "-q", "-b", "main")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "test")
    (root / "VERSION").write_text("2.0.2\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "A")
    return root


def test_a_process_running_another_commit_is_reported_as_a_mismatch(
    answers, monkeypatch, tmp_path
):
    """The definition of done, in the reducer.

    A live component reporting commit A while its checkout is on B is the drift
    v1.28 was built for. It is a WARN, not a failure: the observation is
    complete and the two layers genuinely differ.
    """
    import subprocess

    root = _repository(tmp_path)
    started_from = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
    ).stdout.strip()

    (root / "moved").write_text("b", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t.invalid", "-c", "user.name=t", "commit", "-q", "-m", "B"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    now_at = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
    ).stdout.strip()
    assert now_at != started_from

    answers(_identity(commit=started_from))
    monkeypatch.setattr(runtime_identity, "mq_mcp_root", lambda: root)

    observed = stack_provenance.observe_mq_mcp()
    assert observed is not None
    assessed = stack_provenance.assess(observed)

    assert assessed["running"]["commit"] == started_from
    assert assessed["checkout"]["head"] == now_at
    assert assessed["comparison"]["running_matches_checkout"] is False
    assert "RTP010_RUNNING_CHECKOUT_MISMATCH" in assessed["reasons"]
    assert assessed["status"] == "WARN"


def test_the_action_for_a_stale_process_is_to_restart_it(answers, monkeypatch, tmp_path):
    root = _repository(tmp_path)
    answers(_identity(commit="c" * 40))
    monkeypatch.setattr(runtime_identity, "mq_mcp_root", lambda: root)

    observed = stack_provenance.observe_mq_mcp()
    assert observed is not None
    record = stack_provenance.build([observed])

    assert "restart mq-mcp" in (record["summary"]["next_action"] or "")


# --- the record says whether anyone asked ---------------------------------


def test_the_two_nulls_are_told_apart(refuses, monkeypatch, tmp_path):
    """A CLI that has no process, beside a server that was asked and is not up.

    Both report `running: null`. Only the probe distinguishes them, and the
    difference is real: one says nothing about the component, the other says
    there is nothing to restart.
    """
    root = _repository(tmp_path)
    monkeypatch.setattr(runtime_identity, "mq_mcp_root", lambda: root)

    self_observed = stack_provenance.observe_component()
    asked = stack_provenance.observe_mq_mcp()

    assert asked is not None
    assert self_observed["running"] is asked["running"] is None
    assert self_observed["running_probe"]["attempted"] is False
    assert self_observed["running_probe"]["reachable"] is None
    assert asked["running_probe"]["attempted"] is True
    assert asked["running_probe"]["reachable"] is False


def test_the_contract_refuses_an_identity_nobody_asked_for_beside_a_quiet_one():
    """The rule has to hold per component, not across the array.

    An `if` over `items` is true only when *every* element matches, so the
    record Phase 4 actually produces — one component reporting an identity
    beside one reporting none — would skip the check entirely. A single
    component cannot show that, which is why the earlier version of this test
    passed against a schema that let the two-component form through.
    """
    validator = _provenance_validator()
    cli = {
        "name": "mq-agent",
        "checkout": None,
        "integration": None,
        "remote": None,
        "installed": None,
        "running": None,
        "running_probe": dict(runtime_identity.NOT_PROBED),
        "release": None,
    }
    unasked = {**cli, "name": "mq-mcp", "running": _identity()}

    record = stack_provenance.build([cli, unasked])

    assert list(validator.iter_errors(record)), "an unasked identity validated"


def _provenance_validator() -> Draft202012Validator:
    schema = json.loads(
        runtime_identity._schema_path(runtime_identity.PROVENANCE_SCHEMA).read_text(
            encoding="utf-8"
        )
    )
    return Draft202012Validator(schema, registry=runtime_identity.schema_registry())


def test_the_contract_refuses_an_identity_nobody_asked_for():
    """Schema-enforced, not documented: a reported identity implies a probe."""
    schema = json.loads(
        runtime_identity._schema_path(runtime_identity.PROVENANCE_SCHEMA).read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema, registry=runtime_identity.schema_registry())
    record = stack_provenance.build(
        [
            {
                "name": "mq-mcp",
                "checkout": None,
                "integration": None,
                "remote": None,
                "installed": None,
                "running": _identity(),
                "running_probe": dict(runtime_identity.NOT_PROBED),
                "release": None,
            }
        ]
    )

    assert list(validator.iter_errors(record)), "an unasked identity validated"


def test_a_record_built_without_a_probe_concept_says_so():
    """Null is neither `asked` nor `asked and got nothing`."""
    assessed = stack_provenance.assess(
        {
            "name": "mq-agent",
            "checkout": None,
            "integration": None,
            "remote": None,
            "installed": None,
            "running": None,
            "release": None,
        }
    )

    assert assessed["running_probe"] is None


# --- the consumer adds no identity logic of its own -----------------------


def test_the_consumer_cannot_produce_an_identity_even_if_it_wanted_to():
    """Reduction has no way to observe: it imports nothing that could.

    Checked as imports rather than as words in the source, because a word list
    fails on a reason code that legitimately contains one — `VERSION` appears
    in `RTP011_RELEASE_VERSION_MISMATCH`.
    """
    import ast

    tree = ast.parse(Path(stack_provenance.__file__).read_text(encoding="utf-8"))
    imported = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    for producing in ("subprocess", "importlib", "os", "httpx"):
        assert producing not in imported


def test_what_the_component_said_is_what_is_recorded(answers, monkeypatch):
    reported = _identity(version="9.9.9", commit="d" * 40, install_type="wheel")
    answers(reported)
    monkeypatch.setattr(runtime_identity, "mq_mcp_root", lambda: None)

    component = stack_provenance.observe_mq_mcp()

    assert component is not None
    assert component["running"] == reported
    assert json.dumps(component["running"], sort_keys=True) == json.dumps(
        reported, sort_keys=True
    )
