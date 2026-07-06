"""Codicil command-line interface: `codicil index` and `codicil serve`."""

import argparse
import os
from pathlib import Path

from . import __version__


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="codicil",
        description="Durable, searchable memory of your engineering docs for AI coding assistants.",
    )
    parser.add_argument("--version", action="version", version=f"codicil {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Index a repository's docs into the local store.")
    p_index.add_argument("path", nargs="?", default=".", help="Repository path (default: current dir).")
    p_index.add_argument("--force", action="store_true", help="Reindex all files, ignoring mtime.")

    p_serve = sub.add_parser("serve", help="Run the MCP server for this repository.")
    p_serve.add_argument("path", nargs="?", default=".", help="Repository path (default: current dir).")

    args = parser.parse_args()

    repo = Path(args.path).resolve()
    if not repo.is_dir():
        parser.error(f"not a directory: {repo}")
    # server.py reads config from the environment at import time.
    os.environ["CODICIL_REPO"] = str(repo)

    from . import server  # imported after CODICIL_REPO is set

    if args.command == "index":
        indexed, skipped = server.index_repo(force=args.force)
        # Informational, not a warning — stdout, so `2>/dev/null` silences the
        # embed-failure warning without also hiding this summary.
        print(
            f"Indexed {indexed}, skipped {skipped} "
            f"({server.collection.count()} total chunks) in {repo}."
        )
    elif args.command == "serve":
        server.serve()


if __name__ == "__main__":
    main()
