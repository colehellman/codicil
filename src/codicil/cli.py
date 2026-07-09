"""Codicil command-line interface: `codicil index`, `codicil serve`, and `codicil query`."""

import argparse
import os
import sys
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

    p_query = sub.add_parser("query", help="Search the indexed docs and print matching passages.")
    p_query.add_argument(
        "query", nargs="+",
        help="Natural-language question or keywords. If it starts with '-', "
             "put '--' before it, e.g. `codicil query -- -Wall flag not working`.",
    )
    p_query.add_argument("--repo", dest="path", default=".", help="Repository path (default: current dir).")
    p_query.add_argument("--n-results", type=int, default=5, help="Passages to return, 1-10 (default: 5).")

    args = parser.parse_args()

    repo = Path(args.path).resolve()
    if not repo.is_dir():
        parser.error(f"not a directory: {repo}")
    # server.py reads config from the environment at import time.
    os.environ["CODICIL_REPO"] = str(repo)

    from . import server  # imported after CODICIL_REPO is set

    if args.command == "index":
        server.refuse_if_server_running()
        indexed, skipped = server.index_repo(force=args.force)
        # Informational, not a warning — stdout, so `2>/dev/null` silences the
        # embed-failure warning without also hiding this summary.
        print(
            f"Indexed {indexed}, skipped {skipped} "
            f"({server.collection.count()} total chunks) in {repo}."
        )
    elif args.command == "serve":
        server.serve()
    elif args.command == "query":
        server.refuse_if_server_running()
        if server.collection.count() == 0:
            print(f"codicil: index empty — building from {repo} …", file=sys.stderr)
            server.index_repo()
        print(server.query_docs(" ".join(args.query), n_results=args.n_results))


if __name__ == "__main__":
    main()
