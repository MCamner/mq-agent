"""A bounded repo review can outlast one model request."""
from unittest.mock import MagicMock, patch

import pytest

from mq_agent.tools.mcp_bridge import MCPBridge


@pytest.mark.parametrize("args,budget", [({}, 930), ({"max_files": 1}, 210), ({"max_files": 99}, 3630)])
def test_repo_review_waits_for_its_bounded_model_calls(args, budget):
    response = MagicMock()
    response.json.return_value = {"review": "done"}
    with patch("httpx.post", return_value=response) as post:
        assert MCPBridge().call_tool("review_repo", args) == {"review": "done"}
    assert post.call_args.kwargs["timeout"] == budget
    assert post.call_args.kwargs["json"] == args
    post.assert_called_once()


def test_unrelated_tools_keep_the_existing_timeout():
    response = MagicMock()
    with patch("httpx.post", return_value=response) as post:
        MCPBridge().call_tool("git_status", {})
    assert post.call_args.kwargs["timeout"] == 120
