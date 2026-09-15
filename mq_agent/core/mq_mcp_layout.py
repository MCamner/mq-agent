"""Where mq-mcp is on this machine: one reading of MQ_MCP_DIR, two answers.

`MQ_MCP_DIR` has always been allowed in two shapes, because mq-mcp's repository
holds its Python project in a subdirectory of the same name:

    <repo-root>/            .git, models/, docs/, schemas/
    <repo-root>/mq-mcp/     pyproject.toml, server.py, bridge.py

Consumers ask two different questions of that variable, and both are legitimate:

* **the checkout** — for identity, the commit, and files kept at the root such
  as `models/ollama/Modelfile.mq-learn`;
* **the project** — for anything spawned with `uv --directory`, because that is
  where `server.py` and `bridge.py` live.

Four modules had grown their own reading, each probing for a different marker
or not probing at all, and two of them were already wrong on a machine
configured the other way. `mcp.manager` resolved the repo root as the server
directory, so `uv run mcp run server.py` started where there is no server.py
and the child exited rc=1 — the receiver could never be produced.
`tools.model_runtime` made the opposite assumption and looked for `models/`
under the project directory, reporting "drift not checked" instead of
comparing anything.

The fix is not one resolver returning one path: root and project are different
questions with different correct answers. What is shared is the *reading* —
normalise the variable once, probe once, answer both from the same result, so
the two can never describe different checkouts.

Resolution never consults the current directory. Standing inside an mq-mcp
checkout must not change where a child process is started, or an operator's
answer would depend on which terminal they happened to be in.

Absence is reported rather than invented. A directory that is neither shape
resolves to nothing, and the consumer's own failure path names the path the
operator actually set — `manager.start()` reports a missing directory,
`run_cochange` returns None on the subprocess error.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: Marks the checkout. Present at the repository root and nowhere below it.
ROOT_MARKER = ".git"

#: Marks the runnable project. `bridge.py` and `pyproject.toml` sit beside it,
#: so one probe settles where every child process must run.
PROJECT_MARKER = "server.py"

#: The project's directory name inside the repository.
PROJECT_DIRNAME = "mq-mcp"

#: Where the checkout lives when nothing says otherwise. Computed on each call
#: rather than at import, so a test that relocates home is actually obeyed.
DEFAULT_DIRNAME = "mq-mcp"


@dataclass(frozen=True)
class MqMcpLayout:
    """What `MQ_MCP_DIR` resolved to, and what it could not resolve.

    `configured` is always set — it is the normalised variable itself, kept so
    a consumer can name the path the operator set when neither shape held.
    `root` and `project` are None when no directory carried the marker.
    """

    configured: Path
    root: Path | None
    project: Path | None


def _configured(mq_mcp_dir: str | Path | None = None) -> Path:
    """Normalise the variable once, without touching the filesystem layout."""
    if mq_mcp_dir:
        return Path(mq_mcp_dir).expanduser()
    env = os.environ.get("MQ_MCP_DIR", "")
    if env:
        return Path(env).expanduser()
    return Path.home() / DEFAULT_DIRNAME


def _first_with(marker: str, candidates: tuple[Path, ...]) -> Path | None:
    for candidate in candidates:
        if (candidate / marker).exists():
            return candidate
    return None


def mq_mcp_layout(mq_mcp_dir: str | Path | None = None) -> MqMcpLayout:
    """Resolve both directories from one reading of the variable.

    An explicit argument outranks the environment — the injectable seam
    `run_cochange` already had, kept and made uniform.

    The candidate lists are what makes the two answers consistent: whichever
    shape was configured, the checkout is looked for at the configured path and
    its parent, and the project at the configured path and its `mq-mcp` child.
    Both shapes therefore land on the same pair, and a resolved project is
    always the resolved root's child.
    """
    configured = _configured(mq_mcp_dir)
    return MqMcpLayout(
        configured=configured,
        root=_first_with(ROOT_MARKER, (configured, configured.parent)),
        project=_first_with(PROJECT_MARKER, (configured, configured / PROJECT_DIRNAME)),
    )


def mq_mcp_root(mq_mcp_dir: str | Path | None = None) -> Path | None:
    """mq-mcp's checkout, when this machine has one."""
    return mq_mcp_layout(mq_mcp_dir).root


def mq_mcp_project(mq_mcp_dir: str | Path | None = None) -> Path | None:
    """The directory holding server.py and bridge.py, when one was found."""
    return mq_mcp_layout(mq_mcp_dir).project


def mq_mcp_run_dir(mq_mcp_dir: str | Path | None = None) -> Path:
    """Where a child process must run, falling back to what was configured.

    Always returns a path so a misconfiguration surfaces where it is legible —
    in the caller that tried to start something, naming the operator's own
    path — rather than raising inside an unrelated call.
    """
    resolved = mq_mcp_layout(mq_mcp_dir)
    return resolved.project or resolved.configured
