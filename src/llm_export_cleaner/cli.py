"""Small CLI companion to the desktop cleaner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from llm_export_cleaner.exporter import export_cleaned
from llm_export_cleaner.library import default_database_path, import_export, search, stats


def main() -> None:
    parser = argparse.ArgumentParser(prog="llm-export-cleaner")
    parser.add_argument("--database", type=Path, default=default_database_path())
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--provider", required=True, choices=("chatgpt", "claude", "grok"))
    imp.add_argument("--input", required=True, type=Path)
    find = sub.add_parser("search")
    find.add_argument("query")
    out = sub.add_parser("export")
    out.add_argument("--output", required=True, type=Path)
    out.add_argument("--all", action="store_true")
    out.add_argument("--since-import", type=int)
    sub.add_parser("stats")
    args = parser.parse_args()
    if args.command == "import":
        result = import_export(provider=args.provider, input_path=args.input, database_path=args.database)
    elif args.command == "search":
        result = search(database_path=args.database, query=args.query)
    elif args.command == "export":
        result = export_cleaned(database_path=args.database, output_path=args.output, included_only=not args.all, import_id=args.since_import)
    else:
        result = stats(args.database)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
