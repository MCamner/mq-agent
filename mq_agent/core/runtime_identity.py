"""Which code is this runtime?

`runtime_guard` answers whether a run may write production evidence. This
answers the question underneath it: what is the running code, and can it say so
in a form anyone can check afterwards.

Identity is component + version + commit. Two builds can carry the same semver,
so a version alone does not identify a runtime — and a commit that cannot be
read is recorded as absent rather than taken from the latest tag or a sibling
checkout.

Everything here derives from the imported module and its distribution metadata,
never from the working directory. `mq-agent docs-audit /some/other/repo` must be
judged on the code doing the auditing, which is the rule
`runtime_guard.repository_root()` already follows and is reused for here.

Nothing in this module touches the network.
"""
from __future__ import annotations

import json
import sys
from importlib.metadata import PackageNotFoundError, distribution, version
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .runtime_guard import _probe, repository_root

#: The component this module identifies. Other MQ components report their own.
COMPONENT = "mq-agent"

#: The distribution name, which differs from the package name.
DISTRIBUTION = "mq-agent"

IDENTITY_SCHEMA = "runtime_identity.schema.json"
PROVENANCE_SCHEMA = "stack_provenance.schema.json"


def _schema_path(name: str) -> Path:
    packaged = Path(__file__).resolve().parents[1] / "schemas" / name
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[2] / "schemas" / name


def schema_registry() -> Registry:
    """Both provenance schemas, resolvable by `$id` without the network.

    Provenance embeds runtime identity by reference so there is one definition
    of what a runtime is. The reference is an `https://mq.local/` `$id` that
    resolves to nothing, so a validator built without this registry raises
    rather than fetching — fail-closed, but every consumer needs the registry.
    """
    schemas = [
        json.loads(_schema_path(name).read_text(encoding="utf-8"))
        for name in (IDENTITY_SCHEMA, PROVENANCE_SCHEMA)
    ]
    return Registry().with_resources(
        [(schema["$id"], Resource.from_contents(schema)) for schema in schemas]
    )


def identity_validator() -> Draft202012Validator:
    schema = json.loads(_schema_path(IDENTITY_SCHEMA).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=schema_registry())


def package_version() -> str | None:
    """The installed distribution's version, or None when it cannot be read."""
    try:
        return version(DISTRIBUTION)
    except PackageNotFoundError:
        return None


def module_path() -> Path:
    """The package directory actually imported — not the working directory."""
    return Path(__file__).resolve().parent.parent


def _direct_url() -> dict[str, Any] | None:
    """The PEP 610 record of how this distribution was installed, if any."""
    try:
        raw = distribution(DISTRIBUTION).read_text("direct_url.json")
    except (PackageNotFoundError, OSError):
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def install_source(direct_url: Any) -> tuple[str, str | None]:
    """How this runtime was installed, and the checkout it points at.

    Only what PEP 610 proves is reported, and it proves less than it first
    appears:

    * `dir_info` means a local directory. Only `editable: true` proves an
      editable install; any other directory install is a local build, which is
      neither a wheel nor something this phase can name.
    * `archive_info` covers *both* cases — "When `url` refers to a source
      archive or a wheel, the `archive_info` key MUST be present" — so only a
      URL naming a `.whl` proves a wheel. A source archive is `unknown`.
    * No `direct_url.json` at all means an index install, and that absence does
      not distinguish pip from pipx from `uv tool`.

    `pipx`, `uv-tool` and `pip` stay in the contract's enum for a later phase
    that can prove them. Malformed metadata degrades to `unknown` rather than
    raising: a broken record is a weaker identity, not a failed observation.
    """
    if not isinstance(direct_url, dict):
        return "unknown", None

    raw_url = direct_url.get("url")
    url = raw_url if isinstance(raw_url, str) else ""

    dir_info = direct_url.get("dir_info")
    if isinstance(dir_info, dict):
        if dir_info.get("editable") is not True:
            return "unknown", None
        path = unquote(urlparse(url).path) if url else ""
        return ("editable", path) if path else ("unknown", None)

    if "archive_info" in direct_url:
        return ("wheel", None) if urlparse(url).path.endswith(".whl") else ("unknown", None)

    return "unknown", None


def direct_url_commit(direct_url: Any) -> str | None:
    """The commit a VCS install records about itself.

    PEP 610 requires it: "A `commit_id` key (type `string`) MUST be present,
    containing the exact commit/revision number that was installed." That is
    real provenance even where the install *shape* stays unprovable, so a
    `pip install git+…` can be a verified identity with `install_type` unknown.
    """
    if not isinstance(direct_url, dict):
        return None
    vcs_info = direct_url.get("vcs_info")
    if not isinstance(vcs_info, dict):
        return None
    commit = vcs_info.get("commit_id")
    return commit if isinstance(commit, str) and commit else None


def identity_quality(version: str | None, commit: str | None) -> str:
    """How complete an identity is, by what it actually carries.

    The schema constrains these the same way, so a record cannot claim more
    than it holds.
    """
    if version and commit:
        return "verified"
    if version:
        return "partial"
    return "unknown"


def checkout_head(root: Path) -> str | None:
    """The commit a checkout is on, or None when it cannot be read."""
    head = _probe(root, "rev-parse", "--verify", "HEAD")
    if head is None or head.returncode != 0:
        return None
    return head.stdout.strip() or None


def observe_checkout(root: Path | None = None) -> dict[str, Any] | None:
    """The checkout the running code lives in, or None when there is none.

    An installed wheel has no working tree. That is the canonical case for a
    released runtime, not a suspicious one.
    """
    checkout = root if root is not None else repository_root()
    if checkout is None or not (Path(checkout) / ".git").exists():
        return None
    checkout = Path(checkout)

    head = checkout_head(checkout)
    branch = _probe(checkout, "rev-parse", "--abbrev-ref", "HEAD")
    status = _probe(checkout, "status", "--porcelain")
    return {
        "path": str(checkout),
        "branch": branch.stdout.strip() if branch and branch.returncode == 0 else None,
        "head": head,
        "worktree_clean": (
            not status.stdout.strip() if status and status.returncode == 0 else None
        ),
    }


def build_identity(
    *,
    version: str | None,
    commit: str | None,
    install_type: str,
    source_path: str | None = None,
    executable: str | None = None,
    module: str | None = None,
    started_at: str | None = None,
    component: str = COMPONENT,
) -> dict[str, Any]:
    """Assemble one `mq.runtime-identity.v1` record. No validation, no I/O."""
    return {
        "schema": "mq.runtime-identity.v1",
        "component": component,
        "version": version,
        "commit": commit,
        "install_type": install_type,
        "identity_quality": identity_quality(version, commit),
        "started_at": started_at,
        "executable": executable,
        "module_path": module,
        "source_path": source_path,
    }


def observe_installed() -> dict[str, Any]:
    """Identify the mq-agent runtime executing this call.

    The commit comes from the checkout an editable install points at. A wheel
    carries no commit metadata yet, so its identity is `partial` — weaker, and
    honest about it, rather than filled in from the latest tag.
    """
    direct_url = _direct_url()
    install_type, source_path = install_source(direct_url)

    # A VCS install states its own commit and PEP 610 requires it, so it wins
    # over anything derived. An editable install has no such record, and its
    # commit is whatever its checkout is on right now.
    commit = direct_url_commit(direct_url)
    if commit is None and install_type == "editable" and source_path:
        source = Path(source_path)
        if (source / ".git").exists():
            commit = checkout_head(source)

    return build_identity(
        version=package_version(),
        commit=commit,
        install_type=install_type,
        source_path=source_path,
        executable=sys.executable,
        module=str(module_path()),
    )


def installed_matches_checkout(
    installed_commit: str | None, checkout_head: str | None
) -> bool | None:
    """Whether the installed code is the checkout's code.

    None when either side was not observed — a comparison nobody made is not a
    comparison that failed. Git reports both abbreviated and full hashes, and
    they name the same commit.
    """
    if not installed_commit or not checkout_head:
        return None
    shorter, longer = sorted((installed_commit, checkout_head), key=len)
    return longer.startswith(shorter)
