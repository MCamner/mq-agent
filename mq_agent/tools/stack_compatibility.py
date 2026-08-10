"""Stack compatibility gate — mq.stack-compatibility.v1.

Read-only, deterministic assessment of dependency compatibility across MQ
repositories. Individual repos can be green while the stack still holds a
latent incompatibility: declared ranges, lockfiles and shared protocol tracks
have to agree across repository boundaries, and no single repo's test suite can
prove that.

This module implements the static half of the gate:

* Phase 0 — the `mq.stack-compatibility.v1` report contract.
* Phase 1 — repository inventory: discover repos, read their contracts and
  dependency sources, and report declared and locked versions with provenance.

It never modifies dependencies, lockfiles or working trees. Missing
repositories, files or tools are reported as UNAVAILABLE rather than being
treated as incompatibility.
"""

from __future__ import annotations

import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from mq_agent.tools.stack_tools import MQ_STACK_REPOS, _expand, _version

COMPATIBILITY_SCHEMA = "mq.stack-compatibility.v1"

# Shared dependencies tracked by the first vertical slice. Phase 2 moves this
# declaration into each repository's own contract; it is centralised here only
# until that metadata exists.
DEFAULT_TRACKED: tuple[str, ...] = ("mcp",)

# The first vertical slice named by the roadmap.
SLICE_REPOS: tuple[str, ...] = ("mq-mcp", "mq-image-analyze")

# Directories never searched for dependency sources.
_SKIP_DIRS = {".venv", "venv", "node_modules", "backups", ".git", "__pycache__"}

_STATUS_ORDER = {
    "PASS": 0,
    "SKIPPED": 1,
    "UNAVAILABLE": 2,
    "WARN": 3,
    "FAIL": 4,
}


def _worst(statuses: list[str]) -> str:
    """Return the most severe status, defaulting to PASS for an empty list."""
    if not statuses:
        return "PASS"
    return max(statuses, key=lambda s: _STATUS_ORDER.get(s, 0))


def _relative(path: Path, root: Path) -> str:
    """Repo-relative path for provenance. Never emit absolute or home paths."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def _provenance(repo: str, file: Path, root: Path, field: str, observed: str) -> dict[str, str]:
    return {
        "repo": repo,
        "file": _relative(file, root),
        "field": field,
        "observed": observed,
    }


def _find_sources(root: Path) -> dict[str, Path]:
    """Locate dependency sources in the repo root or one level below.

    mq-mcp nests its package (``mq-mcp/mq-mcp/pyproject.toml``), so a root-only
    search would report it as having no declared dependencies at all.
    """
    found: dict[str, Path] = {}
    wanted = ("pyproject.toml", "uv.lock", "constraints.txt")

    for name in wanted:
        candidate = root / name
        if candidate.is_file():
            found[name] = candidate

    if all(name in found for name in wanted):
        return found

    try:
        children = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        return found

    for child in children:
        if child.name in _SKIP_DIRS or child.name.startswith("."):
            continue
        for name in wanted:
            if name in found:
                continue
            candidate = child / name
            if candidate.is_file():
                found[name] = candidate

    return found


def _declared_spec(pyproject: Path, dependency: str) -> tuple[str | None, str]:
    """Return the declared specifier for `dependency` and the field it came from."""
    target = canonicalize_name(dependency)
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None, ""

    project = data.get("project", {})
    if not isinstance(project, dict):
        return None, ""

    def _match(entries: Any, field: str) -> tuple[str | None, str]:
        if not isinstance(entries, list):
            return None, ""
        for raw in entries:
            if not isinstance(raw, str):
                continue
            try:
                requirement = Requirement(raw)
            except InvalidRequirement:
                continue
            if canonicalize_name(requirement.name) == target:
                return str(requirement.specifier) or None, field
        return None, ""

    spec, field = _match(project.get("dependencies"), "project.dependencies")
    if spec is not None:
        return spec, field

    optional = project.get("optional-dependencies")
    if isinstance(optional, dict):
        for extra in sorted(optional):
            spec, field = _match(
                optional[extra], f"project.optional-dependencies.{extra}"
            )
            if spec is not None:
                return spec, field

    return None, ""


def _locked_version(uv_lock: Path, dependency: str) -> str | None:
    """Return the concrete version pinned by a uv lockfile."""
    target = canonicalize_name(dependency)
    try:
        data = tomllib.loads(uv_lock.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None

    packages = data.get("package")
    if not isinstance(packages, list):
        return None

    for package in packages:
        if not isinstance(package, dict):
            continue
        name = package.get("name")
        version = package.get("version")
        if isinstance(name, str) and canonicalize_name(name) == target:
            return version if isinstance(version, str) else None
    return None


def _constraint_version(constraints: Path, dependency: str) -> str | None:
    """Return a pinned version from a pip constraints file."""
    target = canonicalize_name(dependency)
    try:
        lines = constraints.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for line in lines:
        stripped = line.split("#", 1)[0].strip()
        if not stripped or "==" not in stripped:
            continue
        try:
            requirement = Requirement(stripped)
        except InvalidRequirement:
            continue
        if canonicalize_name(requirement.name) != target:
            continue
        for specifier in requirement.specifier:
            if specifier.operator == "==":
                return specifier.version
    return None


def _is_bounded(spec: str | None) -> bool:
    """True when the declared range excludes the next major version.

    An unbounded range is what let MCP 2.x install against a FastMCP 1.x
    contract, so it is tracked explicitly rather than inferred later.
    """
    if not spec:
        return False
    try:
        specifier_set = SpecifierSet(spec)
    except InvalidSpecifier:
        return False

    majors: list[int] = []
    for specifier in specifier_set:
        if specifier.operator in (">=", ">", "==", "~=", "==="):
            try:
                majors.append(Version(specifier.version).major)
            except InvalidVersion:
                continue

    base = max(majors) if majors else 0
    try:
        probe = Version(f"{base + 1}.0.0")
    except InvalidVersion:  # pragma: no cover - defensive
        return False
    return not specifier_set.contains(probe, prereleases=True)


def _locked_within_declared(locked: str | None, spec: str | None) -> bool | None:
    """Whether the locked version satisfies the declared range."""
    if not locked or not spec:
        return None
    try:
        return SpecifierSet(spec).contains(Version(locked), prereleases=True)
    except (InvalidSpecifier, InvalidVersion):
        return None


def _read_contract(root: Path) -> tuple[dict[str, Any] | None, str]:
    """Read `.mq/repo-contract.json`. Returns (contract, error)."""
    path = root / ".mq" / "repo-contract.json"
    if not path.is_file():
        return None, "missing .mq/repo-contract.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"invalid contract JSON: {exc}"
    if not isinstance(data, dict):
        return None, "contract is not a JSON object"
    return data, ""


def _component(
    entry: dict[str, str],
    tracked: tuple[str, ...],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build one component entry plus any findings it raises."""
    repo = entry["name"]
    root = _expand(entry["path"])
    findings: list[dict[str, Any]] = []

    if not root.exists():
        findings.append(
            {
                "code": "MQC001_REPO_NOT_FOUND",
                "severity": "UNAVAILABLE",
                "repo": repo,
                "message": f"{repo} not found locally — compatibility cannot be assessed",
                "blocks_release": False,
            }
        )
        return (
            {
                "repo": repo,
                "status": "UNAVAILABLE",
                "role": entry.get("role", ""),
                "version": None,
                "contract_present": False,
                "dependencies": [],
                "reason": "repo not found locally",
            },
            findings,
        )

    contract, contract_error = _read_contract(root)
    if contract_error:
        code = (
            "MQC002_CONTRACT_MISSING"
            if contract is None and "missing" in contract_error
            else "MQC003_CONTRACT_INVALID"
        )
        findings.append(
            {
                "code": code,
                "severity": "WARN",
                "repo": repo,
                "message": f"{repo}: {contract_error}",
                "blocks_release": False,
            }
        )

    protocols: dict[str, str] = {}
    if contract:
        raw_protocols = contract.get("compatibility", {})
        if isinstance(raw_protocols, dict):
            candidate = raw_protocols.get("protocols")
            if isinstance(candidate, dict):
                protocols = {
                    str(k): str(v) for k, v in candidate.items() if isinstance(v, str)
                }

    version = _version(root)
    sources = _find_sources(root)
    pyproject = sources.get("pyproject.toml")
    uv_lock = sources.get("uv.lock")
    constraints = sources.get("constraints.txt")

    dependencies: list[dict[str, Any]] = []
    statuses: list[str] = []

    for name in tracked:
        declared: str | None = None
        declared_field = ""
        provenance: list[dict[str, str]] = []

        if pyproject is not None:
            declared, declared_field = _declared_spec(pyproject, name)
            if declared is not None:
                provenance.append(
                    _provenance(repo, pyproject, root, declared_field, declared)
                )

        locked: str | None = None
        if uv_lock is not None:
            locked = _locked_version(uv_lock, name)
            if locked is not None:
                provenance.append(
                    _provenance(repo, uv_lock, root, f"package.{name}.version", locked)
                )

        if locked is None and constraints is not None:
            locked = _constraint_version(constraints, name)
            if locked is not None:
                provenance.append(
                    _provenance(repo, constraints, root, name, locked)
                )

        if declared is None and locked is None:
            # The dependency is simply not used by this repo.
            continue

        if not provenance:  # pragma: no cover - defensive
            continue

        bounded = _is_bounded(declared)
        dependencies.append(
            {
                "name": name,
                "declared": declared,
                "locked": locked,
                "installed": None,
                "resolved": None,
                "bounded": bounded,
                "sources": provenance,
            }
        )

        if declared is not None and not bounded:
            statuses.append("WARN")
            findings.append(
                {
                    "code": "MQC005_DECLARED_RANGE_UNBOUNDED",
                    "severity": "WARN",
                    "repo": repo,
                    "message": (
                        f"{repo} declares {name} as {declared!r}, which does not "
                        "exclude the next major version"
                    ),
                    "blocks_release": False,
                    "evidence": provenance,
                }
            )

        within = _locked_within_declared(locked, declared)
        if within is False:
            statuses.append("FAIL")
            findings.append(
                {
                    "code": "MQC006_LOCKED_OUTSIDE_DECLARED",
                    "severity": "FAIL",
                    "repo": repo,
                    "message": (
                        f"{repo} locks {name}=={locked} outside its declared "
                        f"range {declared!r}"
                    ),
                    "blocks_release": True,
                    "evidence": provenance,
                }
            )

    if pyproject is None and not dependencies:
        findings.append(
            {
                "code": "MQC004_DEPENDENCY_SOURCE_MISSING",
                "severity": "UNAVAILABLE",
                "repo": repo,
                "message": f"{repo}: no pyproject.toml found — declared versions unknown",
                "blocks_release": False,
            }
        )
        statuses.append("UNAVAILABLE")

    component: dict[str, Any] = {
        "repo": repo,
        "status": _worst(statuses),
        "role": entry.get("role", ""),
        "version": None if version == "?" else version,
        "contract_present": contract is not None,
        "dependencies": dependencies,
    }
    if protocols:
        component["protocols"] = protocols

    return component, findings


def _next_action(status: str, findings: list[dict[str, Any]]) -> str:
    if status == "PASS":
        return ""
    for severity in ("FAIL", "WARN", "UNAVAILABLE"):
        for finding in findings:
            if finding["severity"] == severity:
                if severity == "FAIL":
                    return f"Resolve {finding['code']} in {finding['repo']}"
                if severity == "WARN":
                    return f"Declare the actual compatibility boundary in {finding['repo']}"
                return f"Make {finding['repo']} available, then re-run the check"
    return ""


def build_report(
    repos: list[dict[str, str]] | None = None,
    tracked: tuple[str, ...] = DEFAULT_TRACKED,
    slice_only: bool = True,
) -> dict[str, Any]:
    """Assemble an `mq.stack-compatibility.v1` report.

    `slice_only` limits the inventory to the roadmap's first vertical slice
    (mq-mcp and mq-image-analyze). Set it to False to inventory the whole stack.
    """
    entries = repos if repos is not None else MQ_STACK_REPOS
    if slice_only:
        entries = [e for e in entries if e["name"] in SLICE_REPOS]

    components: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    for entry in entries:
        component, component_findings = _component(entry, tracked)
        components.append(component)
        findings.extend(component_findings)

    status = _worst([c["status"] for c in components])

    return {
        "schema": COMPATIBILITY_SCHEMA,
        "status": status,
        "mode": "static",
        "components": components,
        # Producer/consumer assessment is Phase 3; the field stays present and
        # empty so consumers can rely on the shape from v1 onwards.
        "relationships": [],
        "findings": findings,
        "next_action": _next_action(status, findings),
        "checked_at": datetime.now(UTC).isoformat(),
    }


def stack_compatibility(
    repos: list[dict[str, str]] | None = None,
    tracked: tuple[str, ...] = DEFAULT_TRACKED,
    slice_only: bool = True,
) -> str:
    """Return the compatibility report as indented JSON."""
    return json.dumps(build_report(repos, tracked, slice_only), indent=2)
