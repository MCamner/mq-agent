"""Fresh resolve for the stack compatibility gate — Phase 4.

The static half of the gate reads what repositories *declare* and what their
lockfiles *hold*. Neither answers the question that actually broke the stack:
what would a new installation select today? A lockfile can keep a repo green
long after its declared range started admitting an incompatible major.

This module answers that, and only when explicitly asked:

* resolve the declared ranges in a temporary directory outside every working
  tree, using ``uv pip compile`` — nothing is installed into a repo, and no
  lockfile is read or written;
* compare the freshly resolved version with the locked one;
* run each repository's declared import probe against the resolved pin.

Failure classification is the load-bearing part. ``uv`` reports an unreachable
registry, an unsatisfiable interpreter and a genuine range conflict under the
same "No solution found" headline, so network and environment markers are
checked *before* conflict markers and anything unrecognised falls back to
UNAVAILABLE. Unknown is not incompatible.

Scope: only the dependencies the gate tracks are resolved, not the repository's
full dependency set, which would mean building the repository itself. A pin
reported here is therefore what the tracked range alone admits; another
declared dependency could narrow it further.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

# (argv, cwd, timeout) -> (returncode, stdout, stderr)
Runner = Callable[[list[str], Path, int], tuple[int, str, str]]

# Import probes belong to the repositories that own the contract. This is the
# fallback for repos that have not declared theirs yet — the roadmap's initial
# critical import.
DEFAULT_PROBES: dict[str, str] = {
    "mcp": "from mcp.server.fastmcp import FastMCP",
}

RESOLVE_TIMEOUT = 180
PROBE_TIMEOUT = 300

# Sentinel: look uv up on PATH. Passing None explicitly means "not installed".
AUTO_UV = "<auto>"

# uv's wording for a registry it could not reach. Checked before the conflict
# markers, because an offline run prints both.
_NETWORK_MARKERS = (
    "network was disabled",
    "not found in the cache",
    "failed to fetch",
    "error sending request",
    "request failed after",
    "connection refused",
    "connection reset",
    "dns error",
    "temporary failure in name resolution",
    "timed out",
    "certificate",
    "proxy",
    "offline",
)

# Failures of the machinery rather than of the stack: the environment could not
# be built, or the interpreter under test could not be satisfied. uv reports the
# latter through the same "No solution found" headline as a range conflict, so
# these are checked first too.
_ENVIRONMENT_MARKERS = (
    "failed to build",
    "the build backend returned an error",
    "no interpreter found",
    "python version",
    "requires-python",
    "does not satisfy",
    "failed to install",
    "no such file or directory",
    "permission denied",
    "no space left",
)

_CONFLICT_MARKERS = (
    "no solution found",
    "unsatisfiable",
    "is incompatible with",
)

# What a failure of the probed statement itself looks like: Python ran, and the
# repository's declared contract did not hold.
_PYTHON_FAILURE = re.compile(
    r"^\s*(Traceback \(most recent call last\)|[A-Za-z_][A-Za-z0-9_.]*(Error|Exception|Warning):)",
    re.MULTILINE,
)

_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;#]+)")


def _default_runner(argv: list[str], cwd: Path, timeout: int) -> tuple[int, str, str]:
    proc = subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    return proc.returncode, proc.stdout, proc.stderr


def _one_line(text: str, limit: int = 300) -> str:
    collapsed = " ".join(text.split())
    return collapsed[:limit] if collapsed else "no output"


def _unavailable_reason(text: str, markers: tuple[str, ...]) -> str | None:
    """The line carrying the first matching marker, if any.

    Reporting the matched line rather than the first one matters: uv prints its
    generic "No solution found" headline above the real cause, so quoting the
    top of the output would describe an unreachable registry as a conflict.
    """
    lowered = text.lower()
    for marker in markers:
        if marker not in lowered:
            continue
        for line in text.splitlines():
            if marker in line.lower():
                return _one_line(line)
        return _one_line(text)  # pragma: no cover - defensive
    return None


def _classify(returncode: int, stdout: str, stderr: str) -> tuple[str, str]:
    """Map a uv exit into PASS, FAIL or UNAVAILABLE plus a one-line reason."""
    if returncode == 0:
        return "PASS", ""

    text = f"{stderr}\n{stdout}"
    reason = _unavailable_reason(text, _NETWORK_MARKERS + _ENVIRONMENT_MARKERS)
    if reason is not None:
        return "UNAVAILABLE", reason

    if any(marker in text.lower() for marker in _CONFLICT_MARKERS):
        return "FAIL", _one_line(stderr or stdout)

    return "UNAVAILABLE", _one_line(stderr or stdout)


def _parse_pins(stdout: str) -> dict[str, str]:
    """Read `name==version` pins from a compiled requirements listing."""
    pins: dict[str, str] = {}
    for line in stdout.splitlines():
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        match = _PIN.match(line.strip())
        if match:
            pins[canonicalize_name(match.group(1))] = match.group(2)
    return pins


def _finding(
    code: str,
    severity: str,
    repo: str,
    message: str,
    blocks_release: bool,
    evidence: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "repo": repo,
        "message": message,
        "blocks_release": blocks_release,
    }
    if evidence:
        finding["evidence"] = evidence
    return finding


def _python_target(requires_python: str) -> str:
    """Lowest interpreter a `requires-python` specifier admits, e.g. '3.11'.

    The gate's own interpreter is irrelevant to what the repository would
    install. Resolving against it turns an interpreter mismatch into a reported
    range conflict.
    """
    if not requires_python:
        return ""
    try:
        specifier_set = SpecifierSet(requires_python)
    except InvalidSpecifier:
        return ""
    for specifier in specifier_set:
        if specifier.operator in (">=", "==", "~=", ">"):
            try:
                version = Version(specifier.version)
            except InvalidVersion:
                continue
            return f"{version.major}.{version.minor}"
    return ""


def _resolve(
    requirements: list[str], runner: Runner, uv: str, requires_python: str = ""
) -> tuple[dict[str, str], str, str]:
    """Resolve `requirements` in a throwaway directory. Returns (pins, status, reason)."""
    with tempfile.TemporaryDirectory(prefix="mq-fresh-resolve-") as tmp:
        workdir = Path(tmp)
        (workdir / "requirements.in").write_text(
            "\n".join(requirements) + "\n", encoding="utf-8"
        )
        argv = [
            uv,
            "pip",
            "compile",
            "requirements.in",
            "--no-header",
            "--no-annotate",
            "--quiet",
        ]
        python_target = _python_target(requires_python)
        if python_target:
            argv += ["--python-version", python_target]
        try:
            returncode, stdout, stderr = runner(argv, workdir, RESOLVE_TIMEOUT)
        except subprocess.TimeoutExpired:
            return {}, "UNAVAILABLE", f"resolution timed out after {RESOLVE_TIMEOUT}s"
        except OSError as exc:
            return {}, "UNAVAILABLE", _one_line(str(exc))

    status, reason = _classify(returncode, stdout, stderr)
    if status != "PASS":
        return {}, status, reason
    return _parse_pins(stdout), "PASS", ""


def _classify_probe(returncode: int, stdout: str, stderr: str) -> tuple[str, str]:
    """Classify an import probe.

    FAIL requires evidence that Python actually ran and the declared statement
    failed. A non-zero exit on its own is not that evidence: uv exits non-zero
    when it cannot build a wheel or reach the registry, and reading that as a
    broken import would blame the repository for the machine's problem.
    """
    if returncode == 0:
        return "PASS", ""

    # uv's own errors are checked first. A failed wheel build prints the build
    # backend's traceback underneath, so looking for a traceback before ruling
    # out uv would read a broken build machine as a broken contract.
    text = f"{stderr}\n{stdout}"
    reason = _unavailable_reason(text, _NETWORK_MARKERS + _ENVIRONMENT_MARKERS)
    if reason is not None:
        return "UNAVAILABLE", reason

    if _PYTHON_FAILURE.search(text):
        return "FAIL", _one_line(stderr or stdout)

    return "UNAVAILABLE", _one_line(stderr or stdout)


def _probe(
    pin: str, statement: str, runner: Runner, uv: str
) -> tuple[str, str]:
    """Run one import probe against a resolved pin. Returns (status, reason)."""
    with tempfile.TemporaryDirectory(prefix="mq-fresh-probe-") as tmp:
        workdir = Path(tmp)
        argv = [
            uv,
            "run",
            "--isolated",
            "--no-project",
            "--quiet",
            "--with",
            pin,
            "python",
            "-c",
            statement,
        ]
        try:
            returncode, stdout, stderr = runner(argv, workdir, PROBE_TIMEOUT)
        except subprocess.TimeoutExpired:
            return "UNAVAILABLE", f"import probe timed out after {PROBE_TIMEOUT}s"
        except OSError as exc:
            return "UNAVAILABLE", _one_line(str(exc))

    return _classify_probe(returncode, stdout, stderr)


def apply_fresh_resolve(
    components: list[dict[str, Any]],
    runner: Runner | None = None,
    uv_path: str | None = AUTO_UV,
) -> list[dict[str, Any]]:
    """Fill each component's `resolved` versions and return the findings.

    Components that could not be read are skipped; a repo that is not on this
    machine says nothing about what a fresh install would select.
    """
    uv = shutil.which("uv") if uv_path == AUTO_UV else uv_path
    assessable = [
        c
        for c in components
        if c["status"] != "UNAVAILABLE" and c["dependencies"]
    ]
    if not assessable:
        return []

    if not uv:
        return [
            _finding(
                "MQC010_TOOL_UNAVAILABLE",
                "UNAVAILABLE",
                "mq-agent",
                "uv is not installed — a fresh resolution cannot be performed",
                False,
            )
        ]

    run = runner or _default_runner
    findings: list[dict[str, Any]] = []

    for component in assessable:
        findings.extend(_resolve_component(component, run, uv))

    return findings


def _resolve_component(
    component: dict[str, Any], run: Runner, uv: str
) -> list[dict[str, Any]]:
    repo = component["repo"]
    # An empty specifier is still a declaration — and the most exposed one, so
    # it is exactly the case a fresh resolution needs to see.
    declared = [d for d in component["dependencies"] if d["declared"] is not None]
    if not declared:
        return []

    requirements = [f"{d['name']}{d['declared']}" for d in declared]
    pins, status, reason = _resolve(
        requirements, run, uv, component.get("requires_python", "")
    )

    if status == "UNAVAILABLE":
        return [
            _finding(
                "MQC014_FRESH_RESOLVE_UNAVAILABLE",
                "UNAVAILABLE",
                repo,
                f"{repo}: fresh resolution could not be completed — {reason}",
                False,
            )
        ]
    if status == "FAIL":
        return [
            _finding(
                "MQC017_RESOLVE_CONFLICT",
                "FAIL",
                repo,
                f"{repo}: declared ranges cannot be resolved together — {reason}",
                True,
                [s for d in declared for s in d["sources"]],
            )
        ]

    findings: list[dict[str, Any]] = []
    probes = {
        canonicalize_name(key): statement
        for key, statement in component.get("import_probes", {}).items()
    }

    for dependency in declared:
        name = dependency["name"]
        resolved = pins.get(canonicalize_name(name))
        if resolved is None:
            continue
        dependency["resolved"] = resolved

        if dependency["locked"] and dependency["locked"] != resolved:
            findings.append(
                _finding(
                    "MQC015_RESOLVED_DIFFERS_FROM_LOCKED",
                    "WARN",
                    repo,
                    (
                        f"{repo} would install {name}=={resolved} but locks "
                        f"{dependency['locked']} — the lockfile is masking the "
                        "version a fresh install selects"
                    ),
                    False,
                    dependency["sources"],
                )
            )

        statement = probes.get(canonicalize_name(name))
        if not statement:
            continue

        probe_status, probe_reason = _probe(f"{name}=={resolved}", statement, run, uv)
        if probe_status == "FAIL":
            findings.append(
                _finding(
                    "MQC016_IMPORT_PROBE_FAILED",
                    "FAIL",
                    repo,
                    (
                        f"{repo}: {statement!r} fails against the freshly "
                        f"resolved {name}=={resolved} — {probe_reason}"
                    ),
                    True,
                    dependency["sources"],
                )
            )
        elif probe_status == "UNAVAILABLE":
            findings.append(
                _finding(
                    "MQC014_FRESH_RESOLVE_UNAVAILABLE",
                    "UNAVAILABLE",
                    repo,
                    f"{repo}: import probe could not be run — {probe_reason}",
                    False,
                )
            )

    return findings
