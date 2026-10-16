"""Tests for selecting the MCP runtime checkout for every stack command."""

from mq_agent.tools.stack_tools import _DEFAULT_STACK_REPOS, _with_mcp_override


def _path(repos, name):
    return next(x for x in repos if x["name"] == name)["path"]


def test_mcp_runtime_checkout_override():
    repos = _with_mcp_override(_DEFAULT_STACK_REPOS, {"MQ_STACK_MCP_REPO_PATH": "~/mq-mcp-main"})
    assert _path(repos, "mq-mcp") == "~/mq-mcp-main"
    assert _path(repos, "mq-agent") == "~/mq-agent"
    assert _path(_DEFAULT_STACK_REPOS, "mq-mcp") == "~/mq-mcp"


def test_blank_override_keeps_defaults():
    assert _with_mcp_override(_DEFAULT_STACK_REPOS, {"MQ_STACK_MCP_REPO_PATH": "  "}) == _DEFAULT_STACK_REPOS
    assert _with_mcp_override(_DEFAULT_STACK_REPOS, {}) == _DEFAULT_STACK_REPOS


def test_stack_status_and_other_commands_share_inventory():
    import importlib

    status = importlib.import_module("mq_agent.tools.stack_status")
    tools = importlib.import_module("mq_agent.tools.stack_tools")
    assert status.MQ_STACK_REPOS is tools.MQ_STACK_REPOS
