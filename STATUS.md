# Codicil — Status & Handoff

_Last updated: 2026-07-05. This is a working handoff note, not marketing — see `README.md` for the pitch._

## Where it stands: Milestone 1 (prove the idea) — complete

**Goal:** the smallest thing that proves the idea — `codicil index` + `codicil serve` +
a working `query_docs` tool that answers correctly in an MCP client.

### Verified (actually run, not assumed)
- ✅ Installs on Python 3.11.15 — `chromadb 1.5.9`, `mcp 1.28.1` clean (macOS).
- ✅ CLI works: `codicil --version`, `codicil index <path>`, `codicil serve <path>`.
- ✅ **Graceful degradation** — with no embedding host and an empty index, `query_docs`
  returned real results via keyword fallback. Root cause double-checked, not assumed: the
  embed host was confirmed unreachable (`curl` to `localhost:11434` failed to connect) and
  the index was confirmed empty (`.codicil/index_state.json` was `{}`) — both of
  `query_docs`'s fallback trigger conditions were independently verified true.
- ✅ **Live loop inside Claude Code, end-to-end** — `mcp__codicil__query_docs` and
  `mcp__codicil__reindex_docs` confirmed live and callable from a real Claude Code session,
  returning fresh results pulled straight off disk (verified by seeing files created *during
  the session itself* show up in a query result — proves it's reading current state, not a
  stale or mocked index).
- ✅ **Test suite: 12 passing, fully offline** (`pytest -q`), including the headline
  invariant `test_failed_reindex_preserves_old_chunks`.
- ✅ **CI**: GitHub Actions running the test suite on `ubuntu-latest` / Python 3.11, passing
  (first Linux run succeeded — previously only verified on macOS locally).
- ✅ **Public GitHub repo**: `github.com/colehellman/codicil`, confirmed public
  (`gh repo view` → `visibility: PUBLIC`).
- ⚠️ Semantic path (real embeddings via remote Ollama, `nomic-embed-text`) was verified in an
  earlier session per prior notes, not re-verified in this one.

### Open issues (candidates for GitHub issues)
1. **Ranking wobble on vague/short queries.** With `nomic-embed-text`, a vague query can
   rank a loosely-related doc just above the right one (measured previously: 0.611 vs 0.598).
   Returning top-N mitigates it; a reranking step is the real fix. Not yet addressed.
2. **Repo metadata gap.** The public GitHub repo has an empty `description` field
   (confirmed via `gh repo view`) — worth setting for discoverability.
3. ~~Hardcoded relevance threshold~~ — done. `CODICIL_MIN_SCORE` (default 0.5).
4. ~~grep-fallback duplicated snippet lines~~ — done, de-duplicated with regression test.

## Git
- 4 commits on `main`: `04aa7d8` (first pass), `c327424` (threshold/dedup fix + CLAUDE.md/
  STATUS.md), `7691c2e` (gitignore update), `fb54d07` (setup docs + CI, merged via PR #1,
  squashed).
- Remote: `origin` → `git@github.com:colehellman/codicil.git`, public, default branch `main`.
- Working tree clean as of last check.

## Next steps (agreed sequence)
1. ~~Close the live Claude Code loop~~ — done, verified.
2. ~~`docs/SETUP.md`~~ — done, merged (PR #1).
3. ~~Minimal CI~~ — done, merged (PR #1), passing on Linux.
4. ~~Create the public GitHub repo~~ — already existed; confirmed public this session.
5. **Remaining:** demo GIF; publish to PyPI; then the blog post
   *"The Day My Embedding Server Died and Nobody Noticed."* PyPI name `codicil` was checked
   as available in an earlier session (404 on the JSON API) — not re-verified this session.

## Positioning (don't drift)
Sharp, differentiated, reliability-first tool + portfolio piece. The "AI memory" category is
saturated (Engram $98M + many exact-pitch clones), so **do not** frame this as a
category-defining memory platform. Wedge: reliability-first, zero-infra, doc-native. Vision
(durable engineering memory) is the *direction*, not a v1 claim.
