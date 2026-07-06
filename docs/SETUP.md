# Setup

## Prerequisites

**Python 3.11.** `pyproject.toml` declares `>=3.10`, but this repo only tests and supports
3.11 — `chromadb` wheels are unreliable on other versions. The project's own development venv
runs 3.11.15.

## Install

```bash
python3.11 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
```

This installs the core dependencies (`chromadb`, `httpx`, `mcp`) plus `pytest` for the test
suite, and registers the `codicil` console script (`codicil = "codicil.cli:main"`).

Verify:

```bash
./.venv/bin/codicil --version
./.venv/bin/python -m pytest -q
```

The test suite runs fully offline — `embed()`/`embed_many()` are mocked, so no embedding host
is required to get a green run.

## Indexing and serving

```bash
./.venv/bin/codicil index .     # build/update the local index for the current repo
./.venv/bin/codicil serve .     # run the MCP server for the current repo
```

Both subcommands take an optional `path` argument (default: current directory).
`index` also accepts `--force`, which reindexes every file, ignoring recorded modification
times (normal runs are incremental — only files whose mtime changed are re-embedded).

Running `index` first is not required: `serve` builds the index itself on startup if it's
empty. Run `index` explicitly when you want to see indexed/skipped counts up front, or to
force a full reindex before starting the server.

## Configuration

All configuration is read from the environment at import time. Defaults work out of the box
with no setup. (This table mirrors the one in `CLAUDE.md` — keep both in sync if defaults
change in `server.py`.)

| Var | Default | Purpose |
|-----|---------|---------|
| `CODICIL_REPO` | `.` | Repo to index (the CLI sets this from its `path` argument). |
| `CODICIL_STORE` | `<repo>/.codicil` | Where the local Chroma index + state live (gitignored). |
| `CODICIL_EMBED_URL` | `http://localhost:11434` | Ollama-compatible embeddings endpoint. |
| `CODICIL_EMBED_MODEL` | `nomic-embed-text` | Embedding model. |
| `CODICIL_EMBED_WORKERS` | `3` | Concurrent embed requests during indexing. |
| `CODICIL_MIN_SCORE` | `0.5` | Minimum similarity (0–1) for a passage to be returned. |

### Two retrieval paths, same tool call

- **Semantic path** — if `CODICIL_EMBED_URL` points at a reachable Ollama-compatible host and
  the index has embedded chunks, `query_docs` ranks results by embedding similarity and drops
  anything below `CODICIL_MIN_SCORE`.
- **Fallback path** — if the embed host is unreachable, or the index is empty, `query_docs`
  transparently falls back to keyword search read straight off disk. Same tool, same call
  signature, no configuration change required. This is the project's core reliability
  guarantee — see `CLAUDE.md` → "Reliability invariants" if you're modifying indexing or
  retrieval code.

## Using with Claude Code

The committed `.mcp.json` launches the server with no embed URL override, so it defaults to
`localhost:11434` — with no local Ollama running, it operates in fallback (keyword) mode.

To dogfood the semantic path against a remote Ollama host, export an override in your shell
*before* launching Claude Code (stdio MCP servers inherit the parent process's environment):

```bash
export CODICIL_EMBED_URL=http://<your-ollama-host>:11434
claude
```

**Do not** put a private or tailnet hostname into the committed `.mcp.json` or any tracked
file — this repo is public. Keep the committed default as `localhost`.
