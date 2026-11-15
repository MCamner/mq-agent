"""mq-agent runs mq-image-analyze as a subprocess, not through its MCP server.

Every other consumer (mq-mcp, mq-hal) already starts `mq-image` per call, so
the server only had to run for two mq-agent paths. Starting the CLI per call
needs no port, no health check and no idle shutdown, and it cannot reach a
different service that happens to listen on the old port.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from mq_agent.core import config
from mq_agent.tools import image_tools


def _fake_bin(tmp_path: Path, stdout: str = "", stderr: str = "", code: int = 0) -> Path:
    """An executable `mq-image` that records its argv and answers as told."""
    log = tmp_path / "argv.json"
    out = tmp_path / "stdout.txt"
    out.write_text(stdout, encoding="utf-8")
    script = tmp_path / "mq-image"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"json.dump(sys.argv[1:], open({str(log)!r}, 'w'))\n"
        f"sys.stdout.write(open({str(out)!r}).read())\n"
        f"sys.stderr.write({stderr!r})\n"
        f"sys.exit({code})\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def _argv(tmp_path: Path) -> list[str]:
    return json.loads((tmp_path / "argv.json").read_text(encoding="utf-8"))


# ── finding the binary ──────────────────────────────────────────────────────

def test_mq_image_bin_prefers_the_explicit_override(tmp_path, monkeypatch):
    binary = _fake_bin(tmp_path)
    monkeypatch.setenv("MQ_IMAGE_BIN", str(binary))
    assert image_tools.mq_image_bin() == str(binary)


def test_mq_image_bin_falls_back_to_the_checkout_venv(tmp_path, monkeypatch):
    monkeypatch.delenv("MQ_IMAGE_BIN", raising=False)
    monkeypatch.setattr(image_tools.shutil, "which", lambda name: None)
    venv_bin = tmp_path / "mq-image-analyze" / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    _fake_bin(venv_bin)
    monkeypatch.setattr(image_tools.Path, "home", lambda: tmp_path)
    assert image_tools.mq_image_bin() == str(venv_bin / "mq-image")


def test_mq_image_bin_is_none_when_nothing_is_installed(tmp_path, monkeypatch):
    monkeypatch.delenv("MQ_IMAGE_BIN", raising=False)
    monkeypatch.setattr(image_tools.shutil, "which", lambda name: None)
    monkeypatch.setattr(image_tools.Path, "home", lambda: tmp_path)
    assert image_tools.mq_image_bin() is None


# ── observe_architecture ────────────────────────────────────────────────────

OBSERVATION = {"schema_version": "visual_architecture_observation.v1", "image_type": "diagram"}


def test_observe_architecture_runs_the_cli_with_json(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ_IMAGE_BIN", str(_fake_bin(tmp_path, json.dumps(OBSERVATION))))

    assert image_tools.observe_architecture_json("docs/arch.png") == OBSERVATION
    assert _argv(tmp_path) == ["observe-architecture", "docs/arch.png", "--json"]


def test_the_builtin_tool_asks_for_json_too(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ_IMAGE_BIN", str(_fake_bin(tmp_path, json.dumps(OBSERVATION))))

    assert json.loads(image_tools.image_observe_architecture("docs/arch.png")) == OBSERVATION
    assert _argv(tmp_path)[-1] == "--json"


# ── image_perception ────────────────────────────────────────────────────────

PERCEPTION = {"schema_version": "perception.v1", "evidence_id": "sha256:x"}


def test_perception_passes_producer_and_source_type(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ_IMAGE_BIN", str(_fake_bin(tmp_path, json.dumps(PERCEPTION))))

    record = image_tools.image_perception_record("s.png", producer="ocr", source_type="terminal")

    assert record == PERCEPTION
    assert _argv(tmp_path) == ["perceive", "s.png", "--producer", "ocr",
                               "--source-type", "terminal"]


def test_perception_without_source_type_omits_it(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ_IMAGE_BIN", str(_fake_bin(tmp_path, json.dumps(PERCEPTION))))

    image_tools.image_perception_record("s.png", producer="ui")

    assert _argv(tmp_path) == ["perceive", "s.png", "--producer", "ui"]


# ── failures name mq-image-analyze, never mq-mcp ────────────────────────────

@pytest.mark.parametrize("call", [
    lambda: image_tools.observe_architecture_json("a.png"),
    lambda: image_tools.image_perception_record("a.png", producer="ui"),
])
def test_a_missing_install_is_a_clear_error(call, tmp_path, monkeypatch):
    monkeypatch.delenv("MQ_IMAGE_BIN", raising=False)
    monkeypatch.setattr(image_tools.shutil, "which", lambda name: None)
    monkeypatch.setattr(image_tools.Path, "home", lambda: tmp_path)

    result = call()

    assert result["ok"] is False
    assert "mq-image-analyze" in result["error"]
    assert "mq-mcp" not in result["error"]


def test_a_failing_cli_reports_its_stderr(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ_IMAGE_BIN", str(_fake_bin(tmp_path, stderr="File not found: a.png", code=1)))

    result = image_tools.image_perception_record("a.png", producer="ui")

    assert result == {"ok": False, "error": "mq-image perceive failed: File not found: a.png"}


def test_output_that_is_not_a_json_object_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ_IMAGE_BIN", str(_fake_bin(tmp_path, "Image type  diagram")))

    result = image_tools.observe_architecture_json("a.png")

    assert result["ok"] is False
    assert "JSON" in result["error"]


def test_a_hung_cli_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv("MQ_IMAGE_BIN", str(_fake_bin(tmp_path)))

    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="mq-image", timeout=1)

    monkeypatch.setattr(image_tools.subprocess, "run", hang)

    result = image_tools.observe_architecture_json("a.png")

    assert result["ok"] is False
    assert "timed out" in result["error"]


# ── no server is assumed on the old port ────────────────────────────────────

def test_no_mq_image_analyze_server_is_configured_by_default(monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: {})
    assert "mq-image-analyze" not in config.get_mcp_servers()


def test_an_explicitly_configured_server_is_still_honoured(monkeypatch):
    monkeypatch.setattr(
        config, "load_config",
        lambda: {"mcp_servers": {"mq-image-analyze": "http://localhost:9999"}},
    )
    assert config.get_mcp_servers()["mq-image-analyze"] == "http://localhost:9999"


def test_nothing_in_mq_agent_calls_the_image_server_tools():
    root = Path(__file__).resolve().parents[1] / "mq_agent"
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        for needle in ('call_tool("observe_architecture"', '"image_perception", args')
        if needle in path.read_text(encoding="utf-8")
    ]
    assert offenders == []

