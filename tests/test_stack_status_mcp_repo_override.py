"""Tests for selecting the MCP runtime checkout in stack status."""

from mq_agent.tools.stack_status import _status_inventory
from mq_agent.tools.stack_tools import MQ_STACK_REPOS


def test_mcp_runtime_checkout_override(monkeypatch):
    monkeypatch.setenv("MQ_STACK_MCP_REPO_PATH", "~/mq-mcp-main")
    inventory = _status_inventory(None)
    assert next(x for x in inventory if x["name"] == "mq-mcp")["path"] == "~/mq-mcp-main"
    assert next(x for x in MQ_STACK_REPOS if x["name"] == "mq-mcp")["path"] == "~/mq-mcp"
    assert next(x for x in inventory if x["name"] == "mq-agent")["path"] == "~/mq-agent"


def test_explicit_inventory_wins_over_environment(monkeypatch):
    monkeypatch.setenv("MQ_STACK_MCP_REPO_PATH", "~/mq-mcp-main")
    explicit = [{"name": "mq-mcp", "path": "/tmp/test-mcp"}]
    assert _status_inventory(explicit) is explicit


def test_default_inventory_unchanged(monkeypatch):
    monkeypatch.delenv("MQ_STACK_MCP_REPO_PATH", raising=False)
    assert _status_inventory(None) is MQ_STACK_REPOS
