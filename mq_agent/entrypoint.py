"""Console-script bootstrap for mq-agent."""
from __future__ import annotations

from mq_agent.core.credentials import install_openai_api_key

# Resolve credentials before importing mq_agent.main. main.py loads legacy .env
# files with override=False, so a Keychain value installed here cannot be
# replaced by a stale local secret.
install_openai_api_key()

from mq_agent.main import app  # noqa: E402

__all__ = ["app"]
