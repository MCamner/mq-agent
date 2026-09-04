"""A docs audit is told what it is auditing, rather than made to find it.

Guidance was tried first and measured failing: the planner was told that a step
naming one file must not fan out, and three real runs later "Read the README.md
file" still read the first 25 files of the repository root. The ambiguity was in
the task, not in the model's willingness — a model asked to *find* README.md
lists the root, and a later step then reads the listing.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from mq_agent.agents.docs_agent import KNOWN_DOCS, DocsAgent
from mq_agent.core.planner import _FALLBACK_SYSTEM, Planner
from mq_agent.core.state import AgentState, PlanStep


def _repo(tmp_path: Path, *names: str) -> Path:
    for name in names:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# x\n")
    return tmp_path


def test_known_files_are_named_not_discovered(tmp_path) -> None:
    targets = DocsAgent.audit_targets(str(_repo(tmp_path, "README.md", "CHANGELOG.md")))

    assert targets["present"] == [
        str(tmp_path / "README.md"),
        str(tmp_path / "CHANGELOG.md"),
    ]
    assert targets["missing"] == []


def test_an_absent_file_is_a_gap_to_report_not_a_file_to_read(tmp_path) -> None:
    # An audit that quietly omits a missing README hides the most basic finding
    # it exists to make.
    targets = DocsAgent.audit_targets(str(_repo(tmp_path, "README.md")))

    assert targets["missing"] == ["CHANGELOG.md"]
    assert not [path for path in targets["present"] if path.endswith("CHANGELOG.md")]


def test_a_collection_is_offered_only_when_it_exists(tmp_path) -> None:
    without = DocsAgent.audit_targets(str(_repo(tmp_path, "README.md")))
    with_docs = DocsAgent.audit_targets(str(_repo(tmp_path, "docs/guide.md")))

    assert not [c for c in without["collections"] if c["what"].startswith("the documentation")]
    assert [c for c in with_docs["collections"] if c["what"].startswith("the documentation")]


def test_source_files_stay_a_collection(tmp_path) -> None:
    """The distinction the whole fix rests on.

    A named file is supplied directly; a set whose members are not known in
    advance is discovered. Source files are genuinely the second kind, so
    `for_each` belongs there and only there.
    """
    _repo(tmp_path, "pkg/thing.py")

    targets = DocsAgent.audit_targets(str(tmp_path))
    source = [
        c
        for c in targets["collections"]
        if c["discovery"]["args"]["pattern"] == "*.py"
    ]

    assert len(source) == 1
    assert source[0]["discovery"] == {
        "tool": "find_files",
        "args": {"path": str(tmp_path), "pattern": "*.py"},
    }
    assert source[0]["min_items"] == 1


def test_paths_are_given_in_the_callers_frame(tmp_path) -> None:
    # A plan can use these directly; a name relative to some other root cannot
    # be handed to read_file.
    _repo(tmp_path, "README.md")

    targets = DocsAgent.audit_targets(str(tmp_path))

    assert Path(targets["present"][0]).is_file()


def test_the_target_names_are_the_ones_the_audit_claims_to_check() -> None:
    assert KNOWN_DOCS == ("README.md", "CHANGELOG.md")


class _CapturingClient:
    def __init__(self, content: str = '{"steps": []}'):
        self.sent: dict = {}
        self.content = content
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.sent = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


def test_the_targets_reach_the_planner() -> None:
    """Resolved and not sent is the same as not resolved."""
    client = _CapturingClient()
    planner = Planner.__new__(Planner)
    planner.client = client  # type: ignore[assignment]
    planner._model = "test-model"
    planner._system_prompt = _FALLBACK_SYSTEM
    state = AgentState(goal="audit", context={"audit_targets": {"present": ["README.md"]}})

    planner.create_plan(state, ["read_file"])

    sent = json.loads(client.sent["messages"][1]["content"])
    assert sent["context"]["audit_targets"]["present"] == ["README.md"]


def test_declared_discovery_overrides_the_planners_tool_choice() -> None:
    client = _CapturingClient(
        '{"steps": [{"description": "find source", "tool": "list_files", '
        '"args": {"path": ".", "pattern": "*.py"}}]}'
    )
    planner = Planner.__new__(Planner)
    planner.client = client  # type: ignore[assignment]
    planner._model = "test-model"
    planner._system_prompt = _FALLBACK_SYSTEM
    state = AgentState(
        goal="audit",
        context={
            "audit_targets": {
                "collections": [
                    {
                        "what": "source files",
                        "discovery": {
                            "tool": "find_files",
                            "args": {"path": ".", "pattern": "*.py"},
                        },
                        "min_items": 1,
                    }
                ]
            }
        },
    )

    step = planner.create_plan(state, ["list_files", "find_files"])[0]

    assert step.tool == "find_files"
    assert step.args == {"path": ".", "pattern": "*.py"}
    assert step.min_items == 1


def test_the_prompt_says_a_named_target_is_not_discovered() -> None:
    assert "Discovery is for" in _FALLBACK_SYSTEM
    assert "context names a target" in _FALLBACK_SYSTEM


def test_the_task_the_planner_receives_carries_the_targets(tmp_path) -> None:
    _repo(tmp_path, "README.md")
    agent = DocsAgent.__new__(DocsAgent)

    state = agent._audit_state(str(tmp_path))

    assert state.context["audit_targets"] == DocsAgent.audit_targets(str(tmp_path))
    assert "no discovery" in state.goal


def test_the_audit_plans_against_that_task() -> None:
    """Resolved and not used is the same as not resolved.

    Without this, `_audit_state` could be correct, tested, and never called —
    the audit would go back to asking the planner to find its own targets and
    every test above would stay green.
    """
    import inspect

    assert "_audit_state" in inspect.getsource(DocsAgent.audit)


def test_a_collection_with_no_members_is_not_declared(tmp_path) -> None:
    """A target class the repo does not have is not a target.

    Declaring it sends the plan looking for files that are not there, and the
    audit then reports on a set it never had. `docs/` was already conditional;
    the source collection was not.
    """
    _repo(tmp_path, "README.md")

    assert DocsAgent.audit_targets(str(tmp_path))["collections"] == []


def test_a_collection_is_declared_when_its_members_exist(tmp_path) -> None:
    _repo(tmp_path, "README.md", "pkg/thing.py")

    collections = DocsAgent.audit_targets(str(tmp_path))["collections"]

    assert [c["discovery"]["args"]["pattern"] for c in collections] == ["*.py"]


def test_docs_collection_declares_its_discovery_and_cardinality(tmp_path) -> None:
    _repo(tmp_path, "docs/guide.md")

    docs = DocsAgent.audit_targets(str(tmp_path))["collections"][0]

    assert docs["discovery"] == {
        "tool": "find_files",
        "args": {"path": str(tmp_path / "docs"), "pattern": "*"},
    }
    assert docs["min_items"] == 1


def test_docs_audit_output_shows_the_executed_call(tmp_path) -> None:
    readme = _repo(tmp_path, "README.md") / "README.md"
    step = PlanStep(
        index=0,
        description="read README",
        tool="read_file",
        args={"path": str(readme)},
    )
    agent = DocsAgent.__new__(DocsAgent)
    agent.planner = cast(Any, SimpleNamespace(create_plan=lambda state, tools: [step]))
    agent.verifier = cast(Any, SimpleNamespace(
        verify_plan=lambda plan: {"all_passed": True, "failures": []}
    ))

    result = agent.audit(str(tmp_path))

    assert result["steps"][0]["tool"] == "read_file"
    assert result["steps"][0]["args"] == {"path": str(readme)}
    assert result["steps"][0]["for_each"] is None
