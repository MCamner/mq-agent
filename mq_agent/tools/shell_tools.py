import subprocess

BLOCKED = [
    "rm -rf /",
    "sudo rm -rf",
    "mkfs",
    "dd if=",
    "> /dev/sda",
    ":(){ :|:& };:",  # fork bomb
]


def run_command(command: str, cwd: str = ".", timeout: int = 120) -> str:
    """Run a shell command after a minimal denylist check.

    This is not a sandbox: callers must enforce approval and safety policy before
    passing untrusted or write-capable commands. Non-zero exits are returned as
    text instead of raised as exceptions.
    """
    for pattern in BLOCKED:
        if pattern in command:
            raise ValueError(f"Blocked command pattern: '{pattern}'")

    result = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    output = result.stdout
    if result.returncode != 0:
        output += f"\n[exit {result.returncode}] {result.stderr}"
    return output.strip() or "(no output)"


def which(program: str) -> str:
    result = subprocess.run(["which", program], capture_output=True, text=True)
    return result.stdout.strip() or f"{program}: not found"
