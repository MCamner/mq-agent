#!/usr/bin/env python3
"""Assert the local release gate and CI check the same things.

`release-check.sh` is the gate a human runs before cutting a release; the
workflows in `.github/workflows/` are the gate a PR runs. Nothing kept the two
in step, so a check could be added to one and not the other and both would look
green -- the local gate would simply be silent about whatever CI alone covered.

This script compares the two sets of checks and fails when either side gains a
check the other does not have, unless the difference is declared in
EXCEPTIONS below with a reason. Adding a workflow is also a failure until it is
listed in WORKFLOW_SCOPE, so a new gate cannot arrive unnoticed.

Read-only. Run standalone or from release-check.sh.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "release-check.sh"
WORKFLOWS = ROOT / ".github" / "workflows"

# Which workflows carry repo-local checks that the local gate should mirror.
# A workflow set to False is out of scope, and the reason says why.
WORKFLOW_SCOPE: dict[str, str | bool] = {
    "tests.yml": True,
    "markdownlint.yml": True,
    "install-smoke.yml": False,  # packaging: builds a wheel and installs it into a
                                 # clean venv. The local gate runs against the working
                                 # tree and cannot reproduce that without a build.
    "mq-stack-gate.yml": False,  # cross-repo: checks out seven sibling repos and runs
                                 # stack contract/release gates over them. Not a
                                 # repo-local check; see stack-operations.
    "release.yml": False,        # publishes on a tag; runs after the gate, not as one.
}

# Checks allowed to exist on one side only, with the reason they cannot move.
EXCEPTIONS: dict[str, str] = {
    "check-vendored-contracts.py": (
        "CI only: compares against a fresh checkout of mqobsidian main at "
        ".canonical-contracts. The local vault is a working checkout on an "
        "arbitrary branch, so running this locally would report drift that is "
        "not release-relevant."
    ),
    "markdownlint-cli2-action": (
        "CI only as an action; the same lint runs locally through "
        "scripts/markdownlint.sh, which is not part of the release gate "
        "because markdown style never blocks a release."
    ),
}

# Command prefixes that set up an environment rather than check anything.
SETUP_PREFIXES = (
    "uv pip install",
    "uv sync",
    "uv build",
    "uv venv",
    "pip install",
)

# Wrappers to strip before the real command starts.
WRAPPERS = ("uv", "run", "bash", "sh", "python", "python3", "./")


def check_key(command: str) -> str | None:
    """Reduce a shell command to the identity of the check it runs.

    `uv run --extra dev mypy mq_agent/ tests/` and `uv run mypy mq_agent/` are
    the same check with different arguments; both key to "mypy".
    """
    command = command.strip().replace('"', "")
    if not command or command.startswith("#"):
        return None
    if any(command.startswith(p) for p in SETUP_PREFIXES):
        return None

    tokens = command.split()
    while tokens:
        head = tokens[0]
        if head == "--extra":
            del tokens[:2]          # the flag and the extra it names
            continue
        if head.startswith("-") or head in WRAPPERS:
            tokens.pop(0)
            continue
        break
    if not tokens:
        return None

    name = tokens[0].lstrip("./")
    name = name.replace("$ROOT/", "")
    return Path(name).name or None


def local_checks() -> dict[str, str]:
    """Every check release-check.sh runs, keyed by identity."""
    found: dict[str, str] = {}
    for raw in GATE.read_text().splitlines():
        line = raw.strip()
        if not line.startswith("run_check "):
            continue
        rest = line[len("run_check ") :]
        # run_check "LABEL" CMD...  -- drop the quoted label.
        if rest.startswith('"'):
            end = rest.index('"', 1)
            command = rest[end + 1 :]
        else:
            command = rest.split(maxsplit=1)[1] if " " in rest else ""
        key = check_key(command.replace('"$ROOT"/', "").replace("$ROOT/", ""))
        if key:
            found[key] = command.strip()
    return found


def ci_checks(local: dict[str, str]) -> dict[str, str]:
    """Every check CI runs, with ./release-check.sh expanded to the local set."""
    found: dict[str, str] = {}
    unknown = sorted(
        p.name for p in WORKFLOWS.glob("*.yml") if p.name not in WORKFLOW_SCOPE
    )
    if unknown:
        for name in unknown:
            print(f"FAIL: {name} is not listed in WORKFLOW_SCOPE in {Path(__file__).name}")
        raise SystemExit(1)

    for name, in_scope in WORKFLOW_SCOPE.items():
        if not in_scope:
            continue
        path = WORKFLOWS / name
        if not path.exists():
            print(f"FAIL: WORKFLOW_SCOPE lists {name}, which does not exist")
            raise SystemExit(1)
        data = yaml.safe_load(path.read_text()) or {}
        for job in (data.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                uses = step.get("uses")
                if uses and "checkout" not in uses and "setup-uv" not in uses:
                    key = uses.split("@")[0].split("/")[-1]
                    found.setdefault(key, uses)
                command = step.get("run")
                if not command:
                    continue
                for line in str(command).splitlines():
                    key = check_key(line)
                    if not key:
                        continue
                    if key == "release-check.sh":
                        # This job delegates to the local gate; everything the
                        # gate runs is therefore covered by CI. setdefault, not
                        # update: a check CI also runs directly must keep CI's
                        # own command, or the scope comparison below would
                        # compare the local command against itself.
                        for gate_key, gate_command in local.items():
                            found.setdefault(gate_key, gate_command)
                        continue
                    found.setdefault(key, line.strip())
    return found


def main() -> int:
    local = local_checks()
    ci = ci_checks(local)
    failed = False

    for key in sorted(set(ci) - set(local)):
        if key in EXCEPTIONS:
            print(f"SKIP: {key} is CI-only -- {EXCEPTIONS[key]}")
            continue
        print(f"FAIL: CI runs '{key}' and release-check.sh does not")
        failed = True

    for key in sorted(set(local) - set(ci)):
        if key in EXCEPTIONS:
            print(f"SKIP: {key} is local-only -- {EXCEPTIONS[key]}")
            continue
        print(f"FAIL: release-check.sh runs '{key}' and no in-scope workflow does")
        failed = True

    # Same check on both sides is not enough: ruff linted tests/ in CI and only
    # mq_agent/ locally, so a clean local gate said nothing about the CI job.
    for key in sorted(set(local) & set(ci)):
        local_targets = targets(local[key], key)
        ci_targets = targets(ci[key], key)
        if local_targets != ci_targets:
            print(
                f"FAIL: '{key}' runs over {sorted(local_targets) or ['(nothing)']} "
                f"locally and {sorted(ci_targets) or ['(nothing)']} in CI"
            )
            failed = True

    if failed:
        print("check-gate-parity: FAILED")
        return 1
    print(f"PASS: local gate and CI agree on {len(set(local) & set(ci))} checks")
    return 0


def targets(command: str, key: str) -> set[str]:
    """Paths a check runs over, so the same tool with different scope is caught.

    Only arguments count: the tokens after the script or tool itself. A check
    invoked as `bash "$ROOT/scripts/x.sh"` and as `./scripts/x.sh` is the same
    check with the same (empty) scope.
    """
    tokens = [t.replace('"', "").replace("$ROOT/", "") for t in command.split()]
    start = 0
    for i, token in enumerate(tokens):
        if Path(token).name == key:
            start = i + 1
            break
    return {
        token.lstrip("./").rstrip("/")
        for token in tokens[start:]
        if "/" in token and not token.startswith("-")
    }


if __name__ == "__main__":
    sys.exit(main())
