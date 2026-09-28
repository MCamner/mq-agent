#!/usr/bin/env python3
"""Search a local notebook-corpus-index.v1 catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mq_agent.notebook_corpus_search import load_json, search_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--text-hits", type=Path)
    args = parser.parse_args()

    catalog = load_json(args.catalog)
    text_hits = load_json(args.text_hits) if args.text_hits else None
    report = search_catalog(catalog, args.query, top_k=args.top_k, text_hits=text_hits)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
