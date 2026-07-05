# Codicil — Status & Handoff

_Last updated: 2026-07-05. This is a working handoff note, not marketing — see `README.md` for the pitch._

## Where it stands: Milestone 1 (prove the idea) — essentially complete

**Goal:** the smallest thing that proves the idea — `codicil index` + `codicil serve` +
a working `query_docs` tool that answers correctly in an MCP client.

### Verified this session (actually run, not assumed)
- ✅ Installs on Python 3.11.15 — `chromadb 1.5.9`, `mcp 1.28.1` clean.
- ✅ CLI works: `codicil --version`, `codicil index <path>`, `codicil serve <path>`.
- ✅ **Graceful degradation** — with no embedding host and an empty index, `query_docs`
  returned the correct passage via keyword fallback.
- ✅ **Semantic path** — indexed with real `nomic-embed-text` embeddings (over a remote
  Ollama), retrieval + scoring + threshold all work.
- ✅ **MCP server proven end-to-end** — connected a generic MCP client to `codicil serve`,
  it exposed `['query_docs', 'reindex_docs']`, and `query_docs("...graceful degradation...")`
  returned the README's "Reliability by Design" section at score 0.69.
- ✅ **Test suite: 12 passing, fully offline** (`pytest -q`), including the headline
  invariant `test_failed_reindex_preserves_old_chunks`.

### Not yet verified
- ⚠️ **Live loop inside Claude Code** — confirm via `/mcp` that the `codicil` server is
  connected (tools `query_docs`, `reindex_docs`), then ask a cross-doc question and confirm
  it routes through `query_docs` (not Claude's built-in Read). A "what's in the README"
  question does *not* test this — Claude just reads the file. Ask something like
  *"Why is Codicil's reindexing safe if it crashes partway through?"*
  - Note: the committed `.mcp.json` defaults to `localhost:11434`, so without a local Ollama
    it runs grep-only. To dogfood semantic search, see `CLAUDE.md` → "Dogfooding".

## Open issues (candidates for GitHub issues)
1. **Ranking wobble on vague/short queries.** With `nomic-embed-text`, a vague query can
   rank a loosely-related doc just above the right one (measured: 0.611 vs 0.598). Returning
   top-N mitigates it; a reranking step is the real fix. Task prefixes were added and fixed
   *recall* (a relevant doc was being filtered out) but not *ranking*.
2. ~~Hardcoded relevance threshold~~ — **done.** Now `CODICIL_MIN_SCORE` (default 0.5).
3. ~~grep-fallback duplicated snippet lines~~ — **done.** De-duplicated with `…` gap markers;
   regression test added.

## Git
- One commit: `04aa7d8 "first pass"`. **No remote yet.**
- Uncommitted at last check: `src/codicil/server.py`, `tests/test_grep_fallback.py`
  (the issue #2 + #3 changes). Commit them, e.g.:
  `git commit -am "fix: configurable relevance threshold + dedup grep snippets"`

## Next steps (agreed sequence)
1. Close the live Claude Code loop (above) — the true Milestone 1 acceptance test.
2. `docs/SETUP.md` — install + the `CODICIL_EMBED_URL` config, both fallback and semantic.
3. Minimal CI — GitHub Actions running `pytest` (+ ruff/mypy later).
4. Create the public GitHub repo (org `codicil-dev` or personal; `@codicil` GH handle is a
   dormant empty account). PyPI name `codicil` is **available** (verified 404 on the JSON API).
5. Demo GIF; publish to PyPI; then the blog post
   *"The Day My Embedding Server Died and Nobody Noticed."*

## Positioning (don't drift)
Sharp, differentiated, reliability-first tool + portfolio piece. The "AI memory" category is
saturated (Engram $98M + many exact-pitch clones), so **do not** frame this as a
category-defining memory platform. Wedge: reliability-first, zero-infra, doc-native. Vision
(durable engineering memory) is the *direction*, not a v1 claim.
