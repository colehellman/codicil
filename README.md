# Codicil

[![Tests](https://github.com/colehellman/codicil/actions/workflows/test.yml/badge.svg)](https://github.com/colehellman/codicil/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/codicil)](https://pypi.org/project/codicil/)
[![License: MIT](https://img.shields.io/github/license/colehellman/codicil)](LICENSE)

**Durable, searchable documentation for MCP-compatible coding assistants.**

Codicil indexes the documentation already in a repository and exposes two MCP tools:
`query_docs` for retrieval and `reindex_docs` for refreshes. It uses an
Ollama-compatible embedding endpoint when one is available. If the endpoint is unavailable,
search continues with a keyword fallback that reads the current files from disk.

> Status: early, single-user software. The core index and fallback paths are tested, but the
> command-line interface and storage format may change before a stable release.

## What It Does

- Indexes `.md`, `.mdx`, `.rst`, `.txt`, `.yaml`, `.yml`, and `.toml` files.
- Splits Markdown at H1 and H2 headings; other files use overlapping character chunks.
- Stores a local Chroma index in `.codicil/` by default.
- Returns semantic matches when embeddings are available, or keyword matches when they are not.
- Reindexes incrementally using file modification times.

Directories such as `.git`, `.venv`, `node_modules`, `dist`, `build`, and `.codicil` are
excluded. Files with no indexable content are recorded as empty and remove any older chunks.

## Quick Start

Requirements: Python 3.11+ and a Unix-like host. Codicil uses an advisory file lock to protect
its local store.

```bash
python3.11 -m venv .venv
./.venv/bin/pip install -e ".[dev]"

# Optional: works without an embedding server, using keyword fallback.
./.venv/bin/codicil index .
./.venv/bin/codicil serve .
```

`serve` starts the stdio MCP server. If its selected index is empty, it attempts an initial
index automatically. With no reachable embedding endpoint, that initial index skips semantic
embeddings and `query_docs` still searches the files directly.

Run the offline test suite with:

```bash
./.venv/bin/python -m pytest -q
```

## Connect an MCP Client

The repository includes this local Claude Code configuration:

```json
{
  "mcpServers": {
    "codicil": {
      "command": ".venv/bin/codicil",
      "args": ["serve", "."]
    }
  }
}
```

Place equivalent configuration in the repository you want to search, adjusting `command` to the
absolute path of the installed `codicil` executable when necessary. The path passed to `serve`
is the repository Codicil indexes.

Your client can then call:

```text
query_docs(query="How is the reverse proxy configured?", n_results=5)
reindex_docs(force=false)
```

*Illustrative — the Claude Code chat UI isn't something a terminal recording can reproduce.*

![Codicil answering a real query in a terminal, via keyword fallback](docs/demo/demo.gif)

*The GIF above is real, unedited output — the same `query_docs` function called directly in a
terminal instead of over MCP. No local embedding host was running when this was recorded, so
it's answering via keyword fallback, not semantic search — a live demonstration of the
degrade-don't-fail behavior this project is actually about.*

`n_results` should be between 1 and 10. `reindex_docs()` is the supported way to refresh an
index while the MCP server owns the store.

## Embeddings and Fallback

By default Codicil calls `http://localhost:11434/api/embeddings` with the
`nomic-embed-text` model. Start a compatible local service to enable semantic search, then
index the repository:

```bash
export CODICIL_EMBED_URL=http://localhost:11434
export CODICIL_EMBED_MODEL=nomic-embed-text
./.venv/bin/codicil index .
```

For `nomic` models, Codicil automatically uses the recommended document and query task
prefixes. Other model names are sent without prefixes.

If the embedding host cannot be reached, or the selected index has no chunks, `query_docs`
uses keyword search over the repository. Keyword results rank files by matching query terms and
include nearby lines; they are useful but do not understand synonyms or semantic similarity.

Using a remote embedding endpoint sends indexed text and search queries to that endpoint. Keep
the default localhost URL or use an endpoint you trust. Do not commit private hostnames or
credentials in `.mcp.json`.

## Configuration

Configuration is read when the server module starts, so set environment variables before
running `codicil` or launching your MCP client.

| Variable | Default | Meaning |
| --- | --- | --- |
| `CODICIL_REPO` | `.` | Repository to index. The CLI sets this from its path argument. |
| `CODICIL_STORE` | `<repo>/.codicil` | Local Chroma data, index state, and lock file. |
| `CODICIL_EMBED_URL` | `http://localhost:11434` | Base URL of the Ollama-compatible embedding host. |
| `CODICIL_EMBED_MODEL` | `nomic-embed-text` | Embedding model requested from the host. |
| `CODICIL_EMBED_WORKERS` | `3` | Concurrent embedding requests during indexing. |
| `CODICIL_MIN_SCORE` | `0.5` | Minimum semantic similarity score returned by `query_docs`. |

Changing `CODICIL_EMBED_MODEL` selects a separate collection and state file, avoiding
incompatible vector dimensions. Run `codicil index` after changing models; existing collections
remain in the store until you deliberately remove the store while no Codicil process is running.

## Operations and Limitations

`codicil index [path]` indexes a repository and exits. Add `--force` to ignore recorded mtimes
and re-embed every indexable file. `codicil serve [path]` runs the MCP server.

Only one Codicil process may use a store at a time. Starting `codicil index` while `codicil
serve` owns the same store fails intentionally. Use `reindex_docs` from the running MCP server,
or stop the server before running the CLI indexer.

Codicil is currently designed for one local repository and one user. It does not provide file
watching, git hooks, multi-user access, or cross-repository retrieval.

## Troubleshooting

- **“store is already in use”**: another Codicil process owns `CODICIL_STORE`. Stop it, or call
  `reindex_docs` through that running MCP server.
- **Keyword results instead of scores**: the embedding endpoint is unavailable or the selected
  model has not been indexed yet. Check `CODICIL_EMBED_URL`, then run `codicil index`.
- **No matching files**: confirm the file extension is supported and it is not in an excluded
  directory. Queries with only words of two characters or fewer have no fallback search terms.
- **Need a clean rebuild**: stop every Codicil process, then remove the local store and run
  `codicil index`. This permanently removes all local collections for that store.

For development details and reliability invariants, see [CLAUDE.md](CLAUDE.md). For a more
detailed installation guide, see [docs/SETUP.md](docs/SETUP.md).

## License

Released under the [MIT License](LICENSE).
