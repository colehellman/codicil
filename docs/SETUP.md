# Setup

## Install (just want to use it)

```bash
pip install codicil
codicil index .
codicil serve .
```

That's it — see [Configuration](#configuration) below for env vars, or `README.md` for what
it does. Everything below this is for building/testing/contributing to Codicil itself.

## Requirements

- Python 3.11 or newer. The published package metadata requires `>=3.11`.
- A Unix-like operating system. The local-store ownership guard uses `fcntl` advisory locks.
- Optional: an Ollama-compatible service implementing `POST /api/embeddings` for semantic
  search. It is not needed for installation, tests, or keyword fallback.

## Install from source

```bash
python3.11 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
```

The editable install provides the `codicil` command. Verify both the install and offline test
suite:

```bash
./.venv/bin/codicil --version
./.venv/bin/python -m pytest -q
```

Tests replace the embedding functions with deterministic vectors and never require an embedding
host.

## Index a Repository

```bash
./.venv/bin/codicil index /path/to/repository
```

The command scans supported documentation files, sends chunks to the configured embedding host,
and writes local state under `/path/to/repository/.codicil` unless `CODICIL_STORE` is set. A
successful repeat run embeds only files whose modification time changed. Use `--force` to
re-embed all supported files:

```bash
./.venv/bin/codicil index --force /path/to/repository
```

If the embedding endpoint is unavailable, indexing reports skipped files. This does not prevent
the server from answering keyword fallback queries over the current files.

## Run the MCP Server

```bash
./.venv/bin/codicil serve /path/to/repository
```

The server uses stdio, so it is normally launched by an MCP client rather than directly in an
interactive terminal. When its model-specific index is empty, startup attempts an initial
index. To refresh an index while the server is running, call the `reindex_docs` MCP tool.

Do not run `codicil index` against the same store while `serve` is running. The second process
is rejected to prevent Chroma and index-state races.

## Claude Code Configuration

For a repository that contains a local virtual environment, use:

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

If Codicil is installed elsewhere, use an absolute executable path. The `.` argument is resolved
by the process's working directory, so replace it with an absolute repository path if your MCP
client does not start in the intended repository.

## Configure Semantic Search

The defaults target a local Ollama-compatible server:

```bash
export CODICIL_EMBED_URL=http://localhost:11434
export CODICIL_EMBED_MODEL=nomic-embed-text
./.venv/bin/codicil index /path/to/repository
```

`nomic` model names receive `search_document:` and `search_query:` prefixes automatically. If
you change `CODICIL_EMBED_MODEL`, Codicil uses a different Chroma collection and state file.
Run the indexer once for that new model before expecting semantic results.

All environment variables must be available before the server starts. Stdio MCP processes inherit
the environment of the client that launches them.

## Configuration Reference

| Variable | Default | Purpose |
| --- | --- | --- |
| `CODICIL_REPO` | `.` | Repository path. CLI commands set it from their positional path. |
| `CODICIL_STORE` | `<repo>/.codicil` | Directory for Chroma collections, model-specific state, and the lock file. |
| `CODICIL_EMBED_URL` | `http://localhost:11434` | Ollama-compatible embeddings base URL. |
| `CODICIL_EMBED_MODEL` | `nomic-embed-text` | Model passed to the embedding API. |
| `CODICIL_EMBED_WORKERS` | `3` | Number of concurrent requests used when indexing. |
| `CODICIL_MIN_SCORE` | `0.5` | Minimum semantic score for a returned passage. |

## Fallback Behavior

`query_docs` has two modes:

1. Semantic retrieval, when the selected collection contains chunks and the embedding endpoint
   returns a query vector.
2. Keyword fallback, when the endpoint is unreachable or that collection is empty.

Fallback reads supported files directly from disk, so it can surface documents added after the
last semantic index. It performs literal keyword matching, not semantic matching.

## Privacy and Store Management

The default configuration keeps vectors and state local. A remote embedding URL receives the
indexed chunks and queries, so use only an endpoint appropriate for the repository's data.

To discard every local index for a repository, stop all Codicil processes and remove its store
directory. This is destructive; a later index rebuilds only from the repository's current files.
