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
* Phase 2 — declared compatibility: validate the contract's `compatibility`
  block against the repo's own pyproject.toml.
* Phase 3 — relationships: match produced and consumed contracts, and assess
  range overlap and protocol tracks between every pair of repos.

Phase 4 (fresh resolve) is the dynamic half and lives in
`stack_fresh_resolve`; this module calls it only when explicitly asked.

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

from mq_agent.tools.stack_fresh_resolve import (
    AUTO_UV,
    DEFAULT_PROBES,
    Runner,
    apply_fresh_resolve,
)
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
    """Return the declared specifier for `dependency` and the field it came from.

    None means the dependency is not declared at all. An empty string means it
    is declared with no version constraint — the most exposed form there is, so
    it must stay distinguishable from absence rather than collapsing into it.
    """
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
                return str(requirement.specifier), field
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


def _requires_python(pyproject: Path) -> str:
    """The repo's declared `requires-python`, or an empty string."""
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    project = data.get("project")
    if not isinstance(project, dict):
        return ""
    value = project.get("requires-python")
    return value if isinstance(value, str) else ""


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


def _ranges_overlap(left: str | None, right: str | None) -> bool | None:
    """Whether two declared ranges admit at least one common version.

    Emptiness of an arbitrary specifier intersection has no closed form, so the
    ranges are probed on both sides of every version they name: the version
    itself, the next patch, minor and major above it, and a `.dev0` of it,
    which sorts immediately below. Upper-bound-only ranges such as `<2` are
    satisfied only from below, so omitting that probe reported two identical
    ranges as disjoint. `0` covers ranges that name nothing reachable.
    Returns None when either range is absent or unparseable.
    """
    if not left or not right:
        return None
    try:
        left_set = SpecifierSet(left)
        right_set = SpecifierSet(right)
    except InvalidSpecifier:
        return None

    candidates: set[Version] = {Version("0")}
    for specifier in list(left_set) + list(right_set):
        try:
            version = Version(specifier.version)
        except InvalidVersion:
            continue
        candidates.add(version)
        candidates.add(Version(f"{version.major}.{version.minor}.{version.micro + 1}"))
        candidates.add(Version(f"{version.major}.{version.minor + 1}.0"))
        candidates.add(Version(f"{version.major + 1}.0.0"))
        candidates.add(Version(f"{version.public}.dev0"))

    if not candidates:  # pragma: no cover - Version("0") is always present
        return None
    return any(
        left_set.contains(c, prereleases=True) and right_set.contains(c, prereleases=True)
        for c in candidates
    )


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


def _declared_compatibility(contract: dict[str, Any] | None) -> dict[str, Any]:
    """Extract the optional `compatibility` block from a repo contract.

    Absent metadata is normal during rollout and must stay distinguishable from
    metadata that is present but contradicts the repo's own pyproject.toml.
    """
    empty: dict[str, Any] = {
        "present": False,
        "protocols": {},
        "dependencies": {},
        "produces": [],
        "consumes": [],
        "import_probes": dict(DEFAULT_PROBES),
    }
    if not contract:
        return empty

    block = contract.get("compatibility")
    if not isinstance(block, dict):
        return empty

    def _str_map(key: str) -> dict[str, str]:
        raw = block.get(key)
        if not isinstance(raw, dict):
            return {}
        return {str(k): v for k, v in raw.items() if isinstance(v, str)}

    def _str_list(key: str) -> list[str]:
        raw = block.get(key)
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, str)]

    # A repo that declares `import_probes` owns the list outright, including
    # declaring it empty. Only an absent key falls back to the default probe.
    probes = (
        _str_map("import_probes")
        if isinstance(block.get("import_probes"), dict)
        else dict(DEFAULT_PROBES)
    )

    return {
        "present": True,
        "protocols": _str_map("protocols"),
        "dependencies": _str_map("dependencies"),
        "produces": _str_list("produces"),
        "consumes": _str_list("consumes"),
        "import_probes": probes,
    }


def _protocol_major(track: str) -> int | None:
    """Leading major version of a protocol track such as '1.x-fastmcp'."""
    head = track.strip().split(".", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


def _protocol_track_for(dependency: str, protocols: dict[str, str]) -> tuple[str, str] | None:
    """Find the protocol track governing `dependency`, e.g. mcp -> mcp_api."""
    for key, track in protocols.items():
        base = key.rsplit("_", 1)[0] if "_" in key else key
        if canonicalize_name(base) == canonicalize_name(dependency):
            return key, track
    return None


def _specifiers_agree(left: str, right: str) -> bool:
    """Whether two specifiers describe the same boundary.

    Compared as normalised sets rather than strings, so '>=1.27.1,<2' and
    '<2,>=1.27.1' agree.
    """
    try:
        return set(str(s) for s in SpecifierSet(left)) == set(
            str(s) for s in SpecifierSet(right)
        )
    except InvalidSpecifier:
        return False


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

    compatibility = _declared_compatibility(contract)
    protocols = compatibility["protocols"]
    declared_boundaries = compatibility["dependencies"]

    version = _version(root)
    sources = _find_sources(root)
    pyproject = sources.get("pyproject.toml")
    uv_lock = sources.get("uv.lock")
    constraints = sources.get("constraints.txt")
    requires_python = _requires_python(pyproject) if pyproject is not None else ""

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
                        f"{repo} declares {name} with no version constraint at all"
                        if declared == ""
                        else (
                            f"{repo} declares {name} as {declared!r}, which does "
                            "not exclude the next major version"
                        )
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

        # Phase 2: the contract's declared boundary must agree with the code.
        boundary = declared_boundaries.get(name)
        if boundary is None:
            statuses.append("WARN")
            findings.append(
                {
                    "code": "MQC009_COMPATIBILITY_METADATA_MISSING",
                    "severity": "WARN",
                    "repo": repo,
                    "message": (
                        f"{repo} does not declare a compatibility boundary for "
                        f"{name} in .mq/repo-contract.json"
                    ),
                    "blocks_release": False,
                    "evidence": provenance,
                }
            )
        elif declared is not None and not _specifiers_agree(boundary, declared):
            statuses.append("FAIL")
            findings.append(
                {
                    "code": "MQC011_DECLARED_DEPENDENCY_MISMATCH",
                    "severity": "FAIL",
                    "repo": repo,
                    "message": (
                        f"{repo} declares {name} as {boundary!r} in its contract "
                        f"but {declared!r} in pyproject.toml"
                    ),
                    "blocks_release": True,
                    "evidence": provenance,
                }
            )

        track = _protocol_track_for(name, protocols)
        if track is not None:
            key, value = track
            major = _protocol_major(value)
            # An empty specifier is a declaration, not a missing one: it admits
            # every major, so it must reach the check below.
            effective = boundary if boundary is not None else declared
            if major is not None and effective is not None:
                try:
                    allows_next = SpecifierSet(effective).contains(
                        Version(f"{major + 1}.0.0"), prereleases=True
                    )
                except (InvalidSpecifier, InvalidVersion):
                    allows_next = False
                if allows_next:
                    statuses.append("FAIL")
                    findings.append(
                        {
                            "code": "MQC012_PROTOCOL_CONTRADICTS_RANGE",
                            "severity": "FAIL",
                            "repo": repo,
                            "message": (
                                f"{repo} is written against {key}={value!r} but "
                                f"allows {name} {major + 1}.x via {effective!r}"
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
        "compatibility_declared": bool(compatibility["present"]),
        "dependencies": dependencies,
    }
    if protocols:
        component["protocols"] = protocols
    # Keyed by the dependency name as reported, so a contract spelling it
    # "MCP" cannot silently skip its own probe.
    declared_probes = {
        canonicalize_name(key): statement
        for key, statement in compatibility["import_probes"].items()
    }
    probes = {
        d["name"]: declared_probes[canonicalize_name(d["name"])]
        for d in dependencies
        if canonicalize_name(d["name"]) in declared_probes
    }
    if probes:
        component["import_probes"] = probes
    if requires_python:
        component["requires_python"] = requires_python
    if compatibility["produces"]:
        component["produces"] = compatibility["produces"]
    if compatibility["consumes"]:
        component["consumes"] = compatibility["consumes"]

    return component, findings


def _contract_links(
    components: list[dict[str, Any]],
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    """Match consumed contracts to the components that produce them.

    Returns the producer/consumer/contract triples plus the (consumer,
    contract) pairs nothing in the stack produces. A component that both
    produces and consumes a contract satisfies itself and is not reported.
    """
    producers: dict[str, list[str]] = {}
    for component in components:
        for contract in component.get("produces", []):
            producers.setdefault(contract, []).append(component["repo"])

    links: list[tuple[str, str, str]] = []
    unproduced: list[tuple[str, str]] = []

    for component in components:
        consumer = component["repo"]
        for contract in sorted(set(component.get("consumes", []))):
            offering = sorted(producers.get(contract, []))
            if not offering:
                unproduced.append((consumer, contract))
                continue
            links.extend(
                (producer, consumer, contract)
                for producer in offering
                if producer != consumer
            )

    return sorted(links), sorted(unproduced)


def _track_mismatches(
    left: dict[str, Any], right: dict[str, Any]
) -> list[tuple[str, str, str]]:
    """Protocol keys both components declare, with disagreeing tracks."""
    left_tracks = left.get("protocols", {})
    right_tracks = right.get("protocols", {})
    return [
        (key, left_tracks[key], right_tracks[key])
        for key in sorted(set(left_tracks) & set(right_tracks))
        if left_tracks[key] != right_tracks[key]
    ]


def _relationships(
    components: list[dict[str, Any]],
    complete_view: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Assess every producer/consumer and shared-dependency pair in the stack.

    A single repository can be internally consistent while two of them disagree
    across the boundary, which is the whole reason this gate exists. Components
    that could not be read are skipped: unknown is not incompatible.

    `complete_view` is False when the caller narrowed the inventory — with only
    part of the stack in hand, "nobody produces this contract" is not a claim
    the report is entitled to make.
    """
    assessable = sorted(
        (c for c in components if c["status"] != "UNAVAILABLE"),
        key=lambda c: c["repo"],
    )
    findings: list[dict[str, Any]] = []
    links, unproduced = _contract_links(assessable)
    wired = {(producer, consumer) for producer, consumer, _ in links}

    if complete_view and len(assessable) == len(components):
        findings.extend(
            {
                "code": "MQC013_CONTRACT_UNPRODUCED",
                "severity": "WARN",
                "repo": consumer,
                "message": (
                    f"{consumer} consumes {contract!r} but no repository in "
                    "the stack declares it as produced"
                ),
                "blocks_release": False,
            }
            for consumer, contract in unproduced
        )

    relationships: list[dict[str, Any]] = [
        {
            "producer": producer,
            "consumer": consumer,
            "subject": contract,
            "status": "PASS",
            "overlap": None,
            "detail": f"{producer} produces {contract}; {consumer} consumes it",
        }
        for producer, consumer, contract in links
    ]

    for index, left in enumerate(assessable):
        for right in assessable[index + 1 :]:
            left_deps = {d["name"]: d for d in left["dependencies"]}
            right_deps = {d["name"]: d for d in right["dependencies"]}
            pair_wired = (left["repo"], right["repo"]) in wired or (
                right["repo"],
                left["repo"],
            ) in wired

            # Two tracks in the same stack are a warning; two tracks wired to
            # each other are a runtime path that cannot work. This is compared
            # per pair, not per dependency: a repo can target a protocol track
            # without pinning the library itself.
            mismatches = _track_mismatches(left, right)
            mismatch_severity = "FAIL" if pair_wired else "WARN"
            shared = sorted(set(left_deps) & set(right_deps))
            pair_evidence = [
                source
                for name in shared
                for source in left_deps[name]["sources"] + right_deps[name]["sources"]
            ]

            for key, left_track, right_track in mismatches:
                finding: dict[str, Any] = {
                    "code": "MQC008_PROTOCOL_TRACK_MISMATCH",
                    "severity": mismatch_severity,
                    "repo": left["repo"],
                    "message": (
                        f"{left['repo']} targets {key}={left_track!r} but "
                        f"{right['repo']} targets {right_track!r}"
                    ),
                    "blocks_release": pair_wired,
                }
                if pair_evidence:
                    finding["evidence"] = pair_evidence
                findings.append(finding)
                relationships.append(
                    {
                        "producer": left["repo"],
                        "consumer": right["repo"],
                        "subject": key,
                        "status": mismatch_severity,
                        "overlap": None,
                        "detail": (
                            f"{left['repo']} targets {left_track}; "
                            f"{right['repo']} targets {right_track}"
                        ),
                    }
                )

            for name in shared:
                left_dep, right_dep = left_deps[name], right_deps[name]
                left_spec, right_spec = left_dep["declared"], right_dep["declared"]
                overlap = _ranges_overlap(left_spec, right_spec)
                evidence = left_dep["sources"] + right_dep["sources"]
                detail = (
                    f"{left['repo']} declares {name} {left_spec or '—'}; "
                    f"{right['repo']} declares {name} {right_spec or '—'}"
                )

                statuses = []
                if overlap is False:
                    statuses.append("FAIL")
                    findings.append(
                        {
                            "code": "MQC007_DECLARED_RANGES_DISJOINT",
                            "severity": "FAIL",
                            "repo": left["repo"],
                            "message": (
                                f"{left['repo']} declares {name} {left_spec!r} and "
                                f"{right['repo']} declares {right_spec!r} — the "
                                "ranges share no version"
                            ),
                            "blocks_release": True,
                            "evidence": evidence,
                        }
                    )

                # A dependency governed by a disputed protocol track carries
                # that verdict, so no pair renders as PASS above a FAIL.
                governing = _protocol_track_for(name, left.get("protocols", {}))
                if governing is not None and any(
                    key == governing[0] for key, _, _ in mismatches
                ):
                    statuses.append(mismatch_severity)

                relationships.append(
                    {
                        "producer": left["repo"],
                        "consumer": right["repo"],
                        "subject": name,
                        "status": _worst(statuses),
                        "overlap": overlap,
                        "detail": detail,
                    }
                )

    return relationships, findings


# UNAVAILABLE findings that mean "the check itself did not run", as opposed to
# "this repo has nothing to check".
_CHECK_FAILED_CODES = frozenset(
    {"MQC010_TOOL_UNAVAILABLE", "MQC014_FRESH_RESOLVE_UNAVAILABLE"}
)


def _next_action(status: str, findings: list[dict[str, Any]]) -> str:
    if status == "PASS":
        return ""
    # The report's own verdict comes first: a report that says UNAVAILABLE must
    # not point at a warning as the thing to do next.
    order = [status] + [s for s in ("FAIL", "WARN", "UNAVAILABLE") if s != status]
    for severity in order:
        candidates = [f for f in findings if f["severity"] == severity]
        if severity == "UNAVAILABLE":
            # A check that could not run outranks a repo that has nothing to
            # check. Repos without Python dependency sources are permanently
            # UNAVAILABLE by design and would otherwise mask every other cause.
            candidates.sort(key=lambda f: f["code"] not in _CHECK_FAILED_CODES)
        for finding in candidates:
            if severity == "FAIL":
                return f"Resolve {finding['code']} in {finding['repo']}"
            if severity == "WARN":
                return f"Declare the actual compatibility boundary in {finding['repo']}"
            if finding["code"] == "MQC010_TOOL_UNAVAILABLE":
                return "Install uv, then re-run with --fresh-resolve"
            if finding["code"] == "MQC014_FRESH_RESOLVE_UNAVAILABLE":
                return "Re-run --fresh-resolve once the package registry is reachable"
            if finding["code"] == "MQC004_DEPENDENCY_SOURCE_MISSING":
                return (
                    f"{finding['repo']} declares no Python dependencies — "
                    "nothing for this gate to assess"
                )
            return f"Make {finding['repo']} available, then re-run the check"
    return ""


def build_report(
    repos: list[dict[str, str]] | None = None,
    tracked: tuple[str, ...] = DEFAULT_TRACKED,
    slice_only: bool = True,
    fresh_resolve: bool = False,
    runner: Runner | None = None,
    uv_path: str | None = AUTO_UV,
) -> dict[str, Any]:
    """Assemble an `mq.stack-compatibility.v1` report.

    `slice_only` limits the inventory to the roadmap's first vertical slice
    (mq-mcp and mq-image-analyze). Set it to False to inventory the whole stack.

    `fresh_resolve` additionally resolves the declared ranges in a temporary
    directory and probes the declared critical imports. It shells out to `uv`
    and needs a registry, so it runs only when explicitly requested. `runner`
    and `uv_path` exist so that can be driven deterministically in tests.
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

    relationships, relationship_findings = _relationships(
        components, complete_view=not slice_only
    )
    findings.extend(relationship_findings)

    fresh_findings: list[dict[str, Any]] = []
    if fresh_resolve:
        fresh_findings = apply_fresh_resolve(components, runner, uv_path)
        findings.extend(fresh_findings)

    status = _worst(
        [c["status"] for c in components]
        + [f["severity"] for f in relationship_findings]
        + [f["severity"] for f in fresh_findings]
    )

    # _STATUS_ORDER ranks WARN above UNAVAILABLE, which is right for the static
    # gate: a warning is a real observation, an unavailable repo is not. It is
    # wrong here. A resolution the caller explicitly asked for and that never
    # ran must not be reported as a mere warning — that is an exit code of 0 for
    # a check that did not happen. A proven incompatibility still outranks it.
    if (
        fresh_resolve
        and status != "FAIL"
        and any(f["severity"] == "UNAVAILABLE" for f in fresh_findings)
    ):
        status = "UNAVAILABLE"

    return {
        "schema": COMPATIBILITY_SCHEMA,
        "status": status,
        "mode": "fresh-resolve" if fresh_resolve else "static",
        "components": components,
        "relationships": relationships,
        "findings": findings,
        "next_action": _next_action(status, findings),
        "checked_at": datetime.now(UTC).isoformat(),
    }


def stack_compatibility(
    repos: list[dict[str, str]] | None = None,
    tracked: tuple[str, ...] = DEFAULT_TRACKED,
    slice_only: bool = True,
    fresh_resolve: bool = False,
) -> str:
    """Return the compatibility report as indented JSON."""
    return json.dumps(
        build_report(repos, tracked, slice_only, fresh_resolve), indent=2
    )
