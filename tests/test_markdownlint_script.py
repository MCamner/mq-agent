"""Contract tests for the repository markdownlint wrapper."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "markdownlint.sh"


def _fake_markdownlint(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    args_file = tmp_path / "args.txt"
    executable = bin_dir / "markdownlint-cli2"
    executable.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"$ARGS_FILE\"\nexit \"${FAKE_EXIT:-0}\"\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return bin_dir, args_file


def _run(tmp_path: Path, *args: str, exit_code: int = 0) -> subprocess.CompletedProcess[str]:
    bin_dir, args_file = _fake_markdownlint(tmp_path)
    env = os.environ.copy()
    env.update(
        PATH=f"{bin_dir}:{env['PATH']}",
        ARGS_FILE=str(args_file),
        FAKE_EXIT=str(exit_code),
    )
    result = subprocess.run(
        [str(SCRIPT), *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    result.args_file = args_file  # type: ignore[attr-defined]
    return result


def test_defaults_to_all_markdown_files(tmp_path: Path) -> None:
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.args_file.read_text(encoding="utf-8").splitlines() == ["**/*.md"]  # type: ignore[attr-defined]


def test_forwards_arguments_and_exit_code(tmp_path: Path) -> None:
    result = _run(tmp_path, "--fix", "ROADMAP.md", exit_code=7)

    assert result.returncode == 7
    assert result.args_file.read_text(encoding="utf-8").splitlines() == [  # type: ignore[attr-defined]
        "--fix",
        "ROADMAP.md",
    ]
