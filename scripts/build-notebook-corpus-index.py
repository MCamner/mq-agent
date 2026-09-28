#!/usr/bin/env python3
"""Build a local NotebookLM corpus catalog from normalized metadata JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mq_agent.notebook_corpus import materialize


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Normalized metadata JSON input")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args()

    document = json.loads(args.input.read_text(encoding="utf-8"))
    catalog, checkpoint = materialize(
        document,
        catalog_path=args.catalog,
        checkpoint_path=args.checkpoint,
    )
    print(
        "catalog built:",
        f"{checkpoint['included_notebooks']} notebooks,",
        f"{checkpoint['included_items']} items,",
        f"{checkpoint['excluded_items']} excluded,",
        f"sha256={checkpoint['catalog_sha256']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
