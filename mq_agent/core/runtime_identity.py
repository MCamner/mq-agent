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
import os
import re
import sys
from functools import lru_cache
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .runtime_guard import _probe, repository_root

#: The component this module identifies. Other MQ components report their own.
COMPONENT = "mq-agent"

#: The component this one can ask to identify itself. Named here so the probe
#: and the record agree on what they are talking about.
MQ_MCP = "mq-mcp"

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


@lru_cache(maxsize=1)
def identity_validator() -> Draft202012Validator:
    schema = json.loads(_schema_path(IDENTITY_SCHEMA).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=schema_registry())


def package_version(dist: Any = None) -> str | None:
    """The version of the distribution that owns this code, or None.

    Never a distribution that merely shares the name: that would put a
    stranger's version on this runtime's identity.
    """
    if dist is None:
        return None
    try:
        return dist.version or None
    except (AttributeError, ValueError):
        return None


def module_path() -> Path:
    """The package directory actually imported — not the working directory."""
    return Path(__file__).resolve().parent.parent


#: The file this module was loaded from — the subject every claim about the
#: installed runtime is checked against. A directory is a neighbourhood; a file
#: is a thing.
MODULE_FILE = Path(__file__).resolve()


def _within(child: Path, parent: Path) -> bool:
    try:
        return child == parent or child.is_relative_to(parent)
    except (OSError, ValueError):
        return False


def describes_imported_code(
    metadata: Any, subject: Path, owned_files: set[Path] | None
) -> bool:
    """Whether an installed distribution may speak for the code that was
    imported.

    `distribution("mq-agent")` finds a distribution by *name*, and a name is
    not a subject. A virtualenv can hold an installed mq-agent while the
    running code was imported from a checkout somewhere else; its version, its
    commit and its install type would then describe code this process never
    ran. Nothing about the record would look wrong — and an editable stranger
    pointing at another checkout hands over that checkout's HEAD, which reads
    as a mismatch against this one and would refuse a legitimate run.

    Ownership is the distribution's own file list, never the directory it sits
    in: a site-packages holds every distribution in the environment, so "the
    imported file is under the install root" proves only that they are
    neighbours. `RECORD` names what this distribution actually installed.

    An editable install is the exception that carries its own evidence: it
    records the directory it points at, and the imported file has to be inside
    it.
    """
    if isinstance(metadata, dict):
        dir_info = metadata.get("dir_info")
        if isinstance(dir_info, dict) and dir_info.get("editable") is True:
            raw_url = metadata.get("url")
            if not isinstance(raw_url, str) or not raw_url:
                return False
            recorded = unquote(urlparse(raw_url).path)
            return bool(recorded) and _within(subject, Path(recorded))
    return owned_files is not None and subject in owned_files


def _installed_files(dist: Any) -> set[Path] | None:
    """What this distribution installed, resolved. None when it cannot say."""
    try:
        entries = dist.files
    except Exception:
        return None
    if not entries:
        return None
    owned: set[Path] = set()
    for entry in entries:
        try:
            owned.add(Path(str(dist.locate_file(entry))).resolve())
        except (OSError, ValueError):
            continue
    return owned or None


def bound_distribution(subject: Path | None = None) -> tuple[Any, Any] | None:
    """The installed distribution that owns the imported code, if any.

    Everything drawn from installation metadata — version, commit, install
    type — comes through here, so nothing can be bound for one field and
    unbound for another. None is a fact about the runtime, not a failure: a
    checkout run installs nothing, and a distribution that merely shares the
    name owns nothing.
    """
    target = subject or MODULE_FILE
    try:
        dist = distribution(DISTRIBUTION)
    except (PackageNotFoundError, OSError, ValueError):
        return None
    metadata = _read_direct_url(dist)
    if not describes_imported_code(metadata, target, _installed_files(dist)):
        return None
    return dist, metadata


def _read_direct_url(dist: Any) -> dict[str, Any] | None:
    try:
        raw = dist.read_text("direct_url.json")
    except (OSError, ValueError):
        return None
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _direct_url() -> dict[str, Any] | None:
    """The PEP 610 record of the distribution that owns this code, if any."""
    bound = bound_distribution()
    return bound[1] if bound is not None else None


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
    # The system has to be named, not inferred from the shape of the revision.
    # `svn` numbers its revisions, and `1234567` is seven characters that all
    # happen to be valid hex — indistinguishable from an abbreviated SHA to a
    # pattern, and a different thing entirely.
    if vcs_info.get("vcs") != "git":
        return None
    return usable_commit(vcs_info.get("commit_id"))


#: What this contract accepts as a commit: a git object name, lowercase.
#: PEP 610 covers version control systems that number their revisions rather
#: than hashing them — `svn` and `bzr` are in its own list — and such a
#: revision is real provenance this contract cannot express. It is absent
#: rather than coerced into a field whose pattern it fails, which would produce
#: a record this repository's own validator rejects.
_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")


def usable_commit(value: Any) -> str | None:
    """A commit this contract can carry, or None."""
    # `fullmatch`, not `match`: `$` also matches before a trailing newline, so
    # "abcdef1\n" would pass a check meant to be exact.
    return value if isinstance(value, str) and _COMMIT.fullmatch(value) else None


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
    bound = bound_distribution()
    dist = bound[0] if bound is not None else None
    direct_url = bound[1] if bound is not None else None
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
        version=package_version(dist),
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


# --- the checkout's own layers --------------------------------------------
#
# Integration and release are observations of the same checkout the runtime
# came from, so they share the git probes above rather than growing a second
# set. Aggregating several components, deciding a status and choosing a next
# action is a different job and stays out of this module.
#
# Every ref here is the one this machine already has. `origin/main` is never
# fetched: a later phase adds explicit remote verification, and until then an
# unverified remote is the normal state, not staleness.

#: The ref a checkout is measured against, matching `runtime_guard`.
TRUNK = "main"
REMOTE_TRUNK = "origin/main"


def _rev(root: Path, ref: str) -> str | None:
    result = _probe(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _is_ancestor(root: Path, commit: str, ref: str) -> bool | None:
    """Whether `commit` is reachable from `ref`, or None when it cannot be asked."""
    result = _probe(root, "merge-base", "--is-ancestor", commit, ref)
    if result is None or result.returncode not in (0, 1):
        return None
    return result.returncode == 0


def _ahead_behind(root: Path, ref: str) -> tuple[int | None, int | None]:
    result = _probe(root, "rev-list", "--left-right", "--count", f"{ref}...HEAD")
    if result is None or result.returncode != 0:
        return None, None
    parts = result.stdout.split()
    if len(parts) != 2:
        return None, None
    try:
        behind, ahead = int(parts[0]), int(parts[1])
    except ValueError:
        return None, None
    return ahead, behind


def observe_integration(root: Path | None = None) -> dict[str, Any] | None:
    """How a checkout's HEAD relates to the trunk.

    Reported as separate observations rather than reduced to one word, because
    "behind" and "not integrated" call for different actions. Anything that
    cannot be asked — no `origin/main` in a repository that was never cloned —
    is None, which means unobserved and not false.
    """
    checkout = root if root is not None else repository_root()
    if checkout is None or not (Path(checkout) / ".git").exists():
        return None
    checkout = Path(checkout)

    head = _rev(checkout, "HEAD")
    trunk = _rev(checkout, TRUNK)
    remote_trunk = _rev(checkout, REMOTE_TRUNK)

    ahead, behind = (
        _ahead_behind(checkout, REMOTE_TRUNK) if remote_trunk else (None, None)
    )
    return {
        "head_is_main": (head == trunk) if head and trunk else None,
        "head_integrated_in_main": (
            _is_ancestor(checkout, head, TRUNK) if head and trunk else None
        ),
        "head_pushed": (
            _is_ancestor(checkout, head, REMOTE_TRUNK) if head and remote_trunk else None
        ),
        "ahead": ahead,
        "behind": behind,
        "diverged": (
            (ahead > 0 and behind > 0) if ahead is not None and behind is not None else None
        ),
    }


def _ls_remote(root: Path, ref: str) -> str | None:
    """Ask the remote what it holds, without changing anything locally.

    `ls-remote` queries; `fetch` would write refs into the checkout being
    observed. An observation must not alter its subject. None means the remote
    could not be reached — unobserved, not stale.
    """
    result = _probe(root, "ls-remote", "origin", ref)
    if result is None or result.returncode != 0:
        return None
    line = result.stdout.strip().split("\n")[0]
    sha = line.split("\t")[0].strip() if line else ""
    return sha or None


def observe_remote(root: Path | None = None, *, refresh: bool = False) -> dict[str, Any] | None:
    """What this machine knows of the remote, and what it confirmed.

    Without `refresh` nothing is asked and nothing is claimed: the locally known
    `origin/main` is reported as what it is, a ref this machine last saw. With
    `refresh`, the attempt is recorded whether or not it succeeded, so a caller
    can tell "never asked" from "asked and could not reach it".
    """
    checkout = root if root is not None else repository_root()
    if checkout is None or not (Path(checkout) / ".git").exists():
        return None
    checkout = Path(checkout)

    remote_head = _ls_remote(checkout, f"refs/heads/{TRUNK}") if refresh else None
    return {
        "local_origin_main": _rev(checkout, REMOTE_TRUNK),
        "remote_origin_main": remote_head,
        "verification_attempted": refresh,
        "verified": remote_head is not None,
        "verified_at": (
            datetime.now(UTC).isoformat().replace("+00:00", "Z") if remote_head else None
        ),
    }


def declared_version(root: Path) -> str | None:
    """What the repository says its version is, from its own VERSION file."""
    version_file = Path(root) / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def observe_release(root: Path | None = None) -> dict[str, Any] | None:
    """What a checkout declares and has tagged.

    The tag is an observation in its own right, never a source for filling in
    something else: a checkout ahead of its latest tag is the normal state
    between releases, and the tag's commit is not the checkout's.

    `github_release_tag` needs the network, so it stays None here.
    """
    checkout = root if root is not None else repository_root()
    if checkout is None or not (Path(checkout) / ".git").exists():
        return None
    checkout = Path(checkout)

    described = _probe(checkout, "describe", "--tags", "--abbrev=0")
    latest_tag = (
        described.stdout.strip()
        if described is not None and described.returncode == 0
        else None
    ) or None

    tag_commit = _rev(checkout, latest_tag) if latest_tag else None
    return {
        "declared_version": declared_version(checkout),
        "latest_tag": latest_tag,
        "tag_commit": tag_commit,
        # A checkout ahead of its tag is ordinary progress; a tag that is not in
        # this history at all is a real disagreement. Recording which of the two
        # it is keeps the distinction out of whoever reads the record.
        "tag_reachable_from_head": (
            _is_ancestor(checkout, tag_commit, "HEAD") if tag_commit else None
        ),
        "github_release_tag": None,
    }


def _same_commit(one: str | None, other: str | None) -> bool | None:
    if not one or not other:
        return None
    shorter, longer = sorted((one, other), key=len)
    return longer.startswith(shorter)


def release_matches_checkout(
    release: dict[str, Any] | None, head: str | None
) -> bool | None:
    """Whether the latest tag names the commit the checkout is on."""
    return _same_commit((release or {}).get("tag_commit"), head)


def release_matches_installed(
    release: dict[str, Any] | None, installed_commit: str | None
) -> bool | None:
    """Whether the latest tag names the commit the installed runtime is."""
    return _same_commit((release or {}).get("tag_commit"), installed_commit)


#: Where a long-lived MQ component answers `mq.runtime-identity.v1` about
#: itself. mq-mcp binds the local bridge here; the path is its observability
#: route, not an MCP tool.
RUNNING_PATH = "/runtime-identity"

#: Seconds a probe may take. A component that is not running refuses the
#: connection immediately; this bounds the case where something accepts and
#: then says nothing.
PROBE_HTTP_TIMEOUT = 2.0


def mq_mcp_endpoint() -> str:
    """The local bridge address, honouring the same variables mq-mcp reads."""
    host = os.environ.get("MQ_MCP_HOST", "127.0.0.1")
    port = os.environ.get("MQ_MCP_PORT", "8765")
    return f"http://{host}:{port}{RUNNING_PATH}"


def mq_mcp_root() -> Path | None:
    """mq-mcp's checkout, when this machine has one.

    `MQ_MCP_DIR` names the package directory in existing callers, so the
    checkout is its parent when that is where the repository lives.
    """
    raw = os.environ.get("MQ_MCP_DIR", "")
    candidates = (
        [Path(raw).expanduser(), Path(raw).expanduser().parent] if raw
        else [Path.home() / "mq-mcp"]
    )
    for candidate in candidates:
        if (candidate / ".git").exists():
            return candidate
    return None


def probe_running(endpoint: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Ask a component to identify itself, and record that the asking happened.

    Returns what it said and how the asking went. A component that is not
    running is not a fault and not an unknown identity: there is no process, so
    there is nothing whose identity could be unknown. The record says the
    question was asked and nothing answered, which is a different fact from
    nobody asking — a CLI has no process to ask at all.

    Never raises. Provenance observes; it does not fail a run by looking.
    """
    probe: dict[str, Any] = {"attempted": True, "endpoint": endpoint, "reachable": False}
    try:
        import httpx

        response = httpx.get(endpoint, timeout=PROBE_HTTP_TIMEOUT)
    except Exception:
        # Nothing on the other end, or the asking itself failed. Only this
        # branch means nothing answered.
        return None, probe

    # A status code is an answer. A component running a build from before the
    # route existed replies 404, and reporting that as unreachable would make a
    # live process look identical to a stopped one — the opposite of what this
    # probe is for. It answered and could not identify itself, which is an
    # unknown identity rather than an absent one.
    probe["reachable"] = True
    if response.status_code != 200:
        # It answered, but not with a record. Something is running and could
        # not be identified — an unknown identity, not a false one.
        return None, probe
    try:
        reported = response.json()
    except Exception:
        # Something answered, and what it said was not a record. That is a
        # finding about the component, so it travels as an invalid identity
        # rather than as silence.
        return {}, probe
    return (reported if isinstance(reported, dict) else {}), probe


#: What a component reports when nobody asked it anything.
NOT_PROBED: dict[str, Any] = {"attempted": False, "endpoint": None, "reachable": None}
