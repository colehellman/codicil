#!/usr/bin/env python3
"""Demo helper for docs/demo/demo.tape — not a public CLI command.

query_docs is exposed to AI assistants as an MCP tool, not a `codicil` subcommand,
so this script calls it directly to make the demo recording legible in a plain
terminal.
"""
import sys

from codicil import server

if __name__ == "__main__":
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    print(server.query_docs(sys.argv[1], n_results=n))
