# CLAUDE.md

## What this is

**Codicil** — an MCP server that gives AI coding assistants durable, searchable memory of a
repository's docs. Point it at a repo; it indexes the markdown/text/config and exposes a
`query_docs` tool over the Model Context Protocol. Its defining property: **it degrades to
keyword search when the embedding backend is unreachable, instead of failing.** Read
`README.md` for the full thesis.

This is a public, open-source portfolio project. Positioning: **reliability-first,
zero-infra, doc-native** — deliberately *not* "another AI memory platform." Keep it lean.

## Setup

Requires **Python 3.11** (chromadb wheels are reliable there; the repo's venv uses 3.11.15).

```
python3.11 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
```

## Test

Tests run fully offline — `embed()`/`embed_many()` are mocked, so no embedding host is needed.

```
./.venv/bin/python -m pytest -q
```

## Run

```
./.venv/bin/codicil index .     # build/update the index for a repo
./.venv/bin/codicil serve .     # run the MCP server (what .mcp.json launches)
```

## Environment variables (all optional; defaults in `src/codicil/server.py`)

| Var | Default | Purpose |
|-----|---------|---------|
| `CODICIL_REPO` | `.` | Repo to index (the CLI sets this from its path arg). |
| `CODICIL_STORE` | `<repo>/.codicil` | Where Chroma collections, model-specific state, and the lock file live (gitignored). |
| `CODICIL_EMBED_URL` | `http://localhost:11434` | Ollama-compatible embeddings endpoint. |
| `CODICIL_EMBED_MODEL` | `nomic-embed-text` | Embedding model. Nomic task-prefixes auto-apply. |
| `CODICIL_EMBED_WORKERS` | `3` | Concurrent embed requests. |
| `CODICIL_MIN_SCORE` | `0.5` | Min similarity (0–1) for a passage to be returned. |

## Dogfooding with semantic search (local only — never commit this)

The committed `.mcp.json` sets **no** embed URL, so it defaults to `localhost:11434`. To
dogfood against a remote Ollama, export the override in your shell *before* launching Claude
Code (stdio MCP servers inherit the parent env):

```
export CODICIL_EMBED_URL=http://<your-ollama-host>:11434
claude
```

**Do NOT put a private/tailnet hostname in the committed `.mcp.json` or any tracked file.**
This repo is public. Localhost defaults only.

## Reliability invariants — do not break these

These are the point of the project. If you change indexing or retrieval, keep them intact and
keep their tests green (`tests/test_index_swap.py`, `tests/test_grep_fallback.py`,
`tests/test_concurrency_guard.py`):

1. **Degrade, never fail.** No embedding host or empty index → `query_docs` falls back to
   `grep_fallback` off disk. It must never return "nothing" just because embeddings are down.
2. **Add-then-swap.** In `index_repo`, embed and add a new generation before deleting a file's
   old chunks. A failed embed or Chroma write must leave the old index intact — worst case stale,
   never empty.
3. **Incremental by mtime.** Only reindex files whose mtime changed.
4. **Single-writer.** An exclusive store-level advisory lock refuses a second process; the
   reentrant `_index_lock` serializes access among threads in the owning process.
5. **Model isolation.** A model name selects its own Chroma collection and state file. Do not
   collapse them into one collection: embedding dimensions can differ across models.

## Code style

- Keep it small. This is a curation/integration project, not a framework. Resist scope creep
  and "impressive" abstractions — the sophistication lives in the docs and the reliability, not
  in LOC.
- Preserve the "why" comments (the concurrency, embed-swap, and nomic-prefix rationale).
- `set -euo pipefail` in any shell; type hints on Python.

## Status

See `STATUS.md` for current milestone, verified behaviors, and open issues.
