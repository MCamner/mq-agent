import json
from pathlib import Path
from typing import Any

MEMORY_DIR = Path.home() / ".mq-agent"
PERSISTENT_FILE = MEMORY_DIR / "memory.json"


class Memory:
    """Two-level memory: session (ephemeral) and persistent (disk-backed)."""

    def __init__(self):
        self._session: dict[str, Any] = {}
        self._persistent: dict[str, Any] = {}
        self._load()

    def _load(self):
        MEMORY_DIR.mkdir(exist_ok=True)
        if PERSISTENT_FILE.exists():
            try:
                with open(PERSISTENT_FILE) as f:
                    self._persistent = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._persistent = {}

    def _save(self):
        with open(PERSISTENT_FILE, "w") as f:
            json.dump(self._persistent, f, indent=2, default=str)

    def set(self, key: str, value: Any, persistent: bool = False):
        if persistent:
            self._persistent[key] = value
            self._save()
        else:
            self._session[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        # Session takes priority over persistent
        if key in self._session:
            return self._session[key]
        return self._persistent.get(key, default)

    def delete(self, key: str, persistent: bool = False):
        self._session.pop(key, None)
        if persistent:
            self._persistent.pop(key, None)
            self._save()

    def session_dump(self) -> dict:
        return dict(self._session)

    def persistent_dump(self) -> dict:
        return dict(self._persistent)

    def context(self) -> dict:
        """Merged view: persistent overridden by session."""
        return {**self._persistent, **self._session}
