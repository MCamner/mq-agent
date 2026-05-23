#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Installing mq-agent from: $REPO_DIR"

# Check dependencies
if ! command -v uv &>/dev/null; then
    echo "Error: uv not found."
    echo "Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "Error: python3 not found."
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)"; then
    echo "==> Python $PY_VERSION ✓"
else
    echo "Error: Python 3.11+ required (found $PY_VERSION)"
    exit 1
fi

# Install package
cd "$REPO_DIR"
echo "==> Installing dependencies..."
uv pip install -e ".[dev]"

# Verify CLI
echo "==> Verifying installation..."
if command -v mq-agent &>/dev/null; then
    echo "==> mq-agent installed ✓"
    mq-agent --version
else
    echo "Warning: mq-agent CLI not in PATH."
    echo "You may need to activate your virtual environment or add uv's bin dir to PATH."
fi

echo ""
echo "Run 'mq-agent doctor' to verify your environment."
echo "Run 'mq-agent tui' to launch the dashboard."
