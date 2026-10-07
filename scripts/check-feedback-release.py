#!/usr/bin/env python3
"""Release gate for the Feedback Engine v1.30 public/packaging contract."""
from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

import click
import typer
from jsonschema import Draft202012Validator
from packaging.version import Version

ROOT = Path(__file__).resolve().parent.parent
VERSION = Version((ROOT / "VERSION").read_text(encoding="utf-8").strip())
SCHEMAS = {
    "mq.feedback-experiment.v1": "feedback_experiment.schema.json",
    "mq.feedback-report.v1": "feedback_report.schema.json",
    "mq.feedback-comparison.v1": "feedback_comparison.schema.json",
    "mq.feedback-candidate.v1": "feedback_candidate.schema.json",
    "mq.feedback-activation-readiness.v1": "feedback_activation_readiness.schema.json",
    "mq.feedback-approval.v1": "feedback_approval.schema.json",
    "mq.feedback-policy-event.v1": "feedback_policy_event.schema.json",
    "mq.feedback-canary.v1": "feedback_canary.schema.json",
    "mq.feedback-policy-snapshot.v1": "feedback_policy_snapshot.schema.json",
}
PUBLIC_DOCS = (
    ROOT / "docs" / "FEEDBACK_ENGINE.md",
    ROOT / "docs" / "feedback-engine-clients.md",
    ROOT / "docs" / "feedback-engine-release-evidence.md",
)
REQUIRED_FEEDBACK_COMMANDS = {
    "status",
    "inspect",
    "recent",
    "report",
    "run",
    "compare",
    "candidates",
    "candidate",
    "candidate-state",
    "candidate-handoff",
    "activation-readiness",
    "purge",
}
CONTROLLED_ACTIVATION_COMMANDS = {
    "approve",
    "canary-plan",
    "canary-run",
    "canary-status",
    "canary-check",
    "activate",
    "rollback",
    "post-activation-check",
    "policy",
}
FORBIDDEN_AUTONOMOUS_COMMANDS = {
    "activation",
    "policy-activate",
    "auto-route",
}
PRIVATE_PATH = re.compile(r"(?:/Users/[^/\s]+|/home/[^/\s]+|[A-Za-z]:\\\\Users\\\\[^\\\\\s]+)")
SECRET_LIKE = re.compile(
    r"(?:github_pat_[A-Za-z0-9_]{12,}|ghp_[A-Za-z0-9]{12,}|sk-(?:proj|svcacct)-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9]{20,})"
)


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def check_contracts() -> None:
    contract = json.loads((ROOT / ".mq" / "repo-contract.json").read_text(encoding="utf-8"))
    declared = set(contract.get("contracts", []))
    missing = sorted(set(SCHEMAS) - declared)
    if missing:
        fail(f"feedback contracts missing from .mq/repo-contract.json: {missing}")

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    included = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    for schema_id, filename in SCHEMAS.items():
        source = f"schemas/{filename}"
        target = f"mq_agent/schemas/{filename}"
        if included.get(source) != target:
            fail(f"{schema_id} is not force-included in the wheel")
        data = json.loads((ROOT / source).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(data)
    print(f"OK: {len(SCHEMAS)} feedback contracts are declared, valid and packaged")


def check_command_boundary() -> None:
    from mq_agent.main import app

    root = typer.main.get_command(app)
    if not isinstance(root, click.Group):
        fail("mq-agent root is not a command group")
    feedback = root.commands.get("feedback")
    if not isinstance(feedback, click.Group):
        fail("mq-agent feedback command group is missing")
    commands = set(feedback.commands)
    required = set(REQUIRED_FEEDBACK_COMMANDS)
    if VERSION >= Version("1.31.0"):
        required |= CONTROLLED_ACTIVATION_COMMANDS
    missing = sorted(required - commands)
    forbidden = sorted(FORBIDDEN_AUTONOMOUS_COMMANDS & commands)
    if VERSION < Version("1.31.0"):
        forbidden.extend(sorted(CONTROLLED_ACTIVATION_COMMANDS & commands))
    if missing:
        fail(f"feedback command surface is missing: {missing}")
    if forbidden:
        fail(f"feedback command surface violates v{VERSION} boundary: {sorted(set(forbidden))}")
    if VERSION >= Version("1.31.0"):
        print("OK: feedback CLI exposes human-gated task-class activation without autonomous activation")
    else:
        print("OK: feedback CLI is stable and contains no activation command")


def check_public_docs() -> None:
    for path in PUBLIC_DOCS:
        if not path.is_file():
            fail(f"public Feedback Engine doc is missing: {path.relative_to(ROOT)}")
        text = path.read_text(encoding="utf-8")
        if PRIVATE_PATH.search(text):
            fail(f"private machine path leaked into {path.relative_to(ROOT)}")
        if SECRET_LIKE.search(text):
            fail(f"secret-like token leaked into {path.relative_to(ROOT)}")
        for captured in ("SECRET-TASK-BODY", "PRIVATE-STDOUT", "PRIVATE-STDERR"):
            if captured in text:
                fail(f"captured test/task data leaked into {path.relative_to(ROOT)}")
    print("OK: Feedback Engine public docs are public-safe")


def check_release_surfaces() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    checklist = (ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
    if "## Feedback Engine" not in readme:
        fail("README has no Feedback Engine section")
    if "Feedback Engine F5" not in changelog or "Feedback Engine F6" not in changelog:
        fail("CHANGELOG does not describe F5/F6")
    for required in (
        "stack contract-check",
        "stack protection-check",
        "release-check.sh",
        "main CI",
    ):
        if required not in checklist:
            fail(f"release checklist does not require {required!r}")
    if VERSION >= Version("1.31.0") and "Evidence-Gated Activation" not in changelog:
        fail("CHANGELOG does not describe the v1.31 Evidence-Gated Activation boundary")
    if VERSION >= Version("1.32.0") and "Canary v2" not in changelog:
        fail("CHANGELOG does not describe the v1.32 Canary v2 boundary")
    if VERSION >= Version("1.33.0") and "Policy Registry v2" not in changelog:
        fail("CHANGELOG does not describe the v1.33 Policy Registry v2 boundary")
    print(f"OK: README, changelog and pre-tag checklist carry the v{VERSION} boundary")


def main() -> int:
    check_contracts()
    check_command_boundary()
    check_public_docs()
    check_release_surfaces()
    print(f"PASS: Feedback Engine v{VERSION} release contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())
