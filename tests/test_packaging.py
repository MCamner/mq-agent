"""The built wheel really contains what `pyproject.toml` says it does.

A `force-include` line is an intention. v1.27 shipped
`execution_outcome.schema.json` without one: the loader fell back to the repo
root, every test passed from a checkout, and every installed runtime silently
recorded nothing. The declaration and the artefact had drifted apart and no gate
compared them.

These tests compare them. One reads the declaration and looks inside a real
wheel; the other asks the opposite question — is every schema the runtime loads
actually declared — so a new packaged resource cannot be added without its line.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Schema files are loaded from `mq_agent/schemas/` when installed, falling back
#: to the repo root in a checkout. The fallback is why a missing declaration is
#: invisible locally.
PACKAGED_SCHEMA_DIR = "mq_agent/schemas"


def _force_include() -> dict[str, str]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    wheel = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]
    return wheel["force-include"]


@pytest.fixture(scope="session")
def wheel(tmp_path_factory) -> Path:
    """Build the wheel once and hand back the archive."""
    if shutil.which("uv") is None:
        pytest.skip("uv is required to build the wheel")
    out = tmp_path_factory.mktemp("wheel")
    build = subprocess.run(
        ["uv", "build", "--wheel", str(ROOT), "-o", str(out)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert build.returncode == 0, build.stderr
    built = sorted(out.glob("*.whl"))
    assert len(built) == 1, f"expected one wheel, got {built}"
    return built[0]


def test_every_force_included_file_ships_in_the_wheel(wheel) -> None:
    packed = set(zipfile.ZipFile(wheel).namelist())

    missing = sorted(dest for dest in _force_include().values() if dest not in packed)

    assert not missing, f"declared in pyproject but absent from the wheel: {missing}"


def test_every_force_included_source_exists() -> None:
    """A line pointing at a file that is gone packages nothing and says nothing."""
    missing = sorted(src for src in _force_include() if not (ROOT / src).is_file())

    assert not missing, f"force-include names files that do not exist: {missing}"


# The opposite direction. The wheel test proves the declaration was honoured;
# this proves the declaration exists at all — which is the half that was missing
# when execution_outcome.schema.json shipped broken.
def test_every_schema_the_runtime_loads_is_declared() -> None:
    declared = {Path(dest).name for dest in _force_include().values()}
    loaded = {
        name
        for path in (ROOT / "mq_agent").rglob("*.py")
        for name in re.findall(r'"([\w.-]+\.schema\.json)"', path.read_text(encoding="utf-8"))
    }

    undeclared = sorted(loaded - declared)

    assert not undeclared, (
        "loaded by mq_agent but not force-included, so absent from the wheel: "
        f"{undeclared}"
    )


def test_the_packaged_schemas_are_readable_json(wheel) -> None:
    """Present is not the same as intact."""
    import json

    archive = zipfile.ZipFile(wheel)
    packaged = [n for n in archive.namelist() if n.startswith(f"{PACKAGED_SCHEMA_DIR}/")]

    assert packaged, "the wheel carries no packaged schemas at all"
    for name in packaged:
        json.loads(archive.read(name).decode("utf-8"))
