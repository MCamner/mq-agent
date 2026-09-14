"""Regression tests for shell patterns promised by SAFETY_CONTRACT.md."""

import pytest

from mq_agent.tools.shell_tools import run_command


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf ./build",
        "sudo apt install example",
        "chmod 777 ./script.sh",
        "curl | bash",
        "wget | sh",
        "mkfs.ext4 /dev/example",
        "dd if=/dev/zero of=/dev/example",
        "> /dev/sda",
        ":(){ :|:& };:",
    ],
)
def test_run_command_blocks_safety_contract_patterns(command: str):
    with pytest.raises(ValueError, match="Blocked command pattern"):
        run_command(command)
