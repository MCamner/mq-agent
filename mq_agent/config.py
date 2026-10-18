"""Runtime configuration for mq-agent.

Config is loaded from ~/.mq-agent/config.json and merged with environment
variables and CLI flags. The priority order (highest to lowest) is:

  CLI flags > environment variables > config.json > built-in defaults

Schema: config.json
{
  "safety_mode": "suggest",     // "read-only" | "suggest" | "execute" | "dangerous"
  "provider": "ollama",
  "model": "qwen3.5:9b",            // overridden by MQ_AGENT_MODEL env var
  "dry_run": false,             // default dry-run state
  "working_dir": "."            // default working directory
}
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

_CONFIG_PATH = Path.home() / ".mq-agent" / "config.json"

_VALID_SAFETY_MODES = {"read-only", "suggest", "execute", "dangerous"}
_DEFAULT_MODEL = "qwen3.5:9b"


@dataclass
class MqAgentConfig:
    safety_mode: str = "suggest"
    model: str = _DEFAULT_MODEL
    provider: str = "ollama"
    dry_run: bool = False
    working_dir: str = "."

    def __post_init__(self) -> None:
        if self.safety_mode not in _VALID_SAFETY_MODES:
            raise ValueError(
                f"Invalid safety_mode {self.safety_mode!r}. "
                f"Must be one of: {sorted(_VALID_SAFETY_MODES)}"
            )

    def effective_provider(self) -> str:
        provider = os.environ.get("MQ_AGENT_PROVIDER", self.provider).strip().lower()
        if provider not in {"ollama", "openai"}:
            raise ValueError("Unknown provider; select ollama or openai explicitly")
        return provider

    def effective_model(self) -> str:
        """Return model, preferring MQ_AGENT_MODEL env var over config."""
        explicit = os.environ.get("MQ_AGENT_MODEL")
        if explicit:
            return explicit
        if self.effective_provider() == "openai":
            return self.model if self.model != _DEFAULT_MODEL else "gpt-4o"
        # Ignore legacy cloud-only config unless the provider is explicitly cloud.
        if self.model.startswith(("gpt-", "o1", "o3", "o4")):
            return _DEFAULT_MODEL
        return self.model

    def to_dict(self) -> dict:
        return asdict(self)


def load_config(path: Path = _CONFIG_PATH) -> MqAgentConfig:
    """Load config from disk, falling back to defaults if absent or invalid."""
    if not path.exists():
        return MqAgentConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return MqAgentConfig(
            safety_mode=data.get("safety_mode", "suggest"),
            model=data.get("model", _DEFAULT_MODEL),
            provider=data.get("provider", "ollama"),
            dry_run=bool(data.get("dry_run", False)),
            working_dir=data.get("working_dir", "."),
        )
    except (json.JSONDecodeError, ValueError):
        return MqAgentConfig()


def save_config(config: MqAgentConfig, path: Path = _CONFIG_PATH) -> None:
    """Write config to disk, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
