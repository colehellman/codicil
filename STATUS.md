# Codicil — Status & Handoff

_Last updated: 2026-07-07. This is a working handoff note, not marketing — see `README.md` for the pitch._

## Where it stands: Milestone 1 (prove the idea) — complete

**Goal:** the smallest thing that proves the idea — `codicil index` + `codicil serve` +
a working `query_docs` tool that answers correctly in an MCP client.

### Verified (actually run, not assumed)
- ✅ Installs on Python 3.11.15 — `chromadb 1.5.9`, `mcp 1.28.1` clean (macOS).
- ✅ CLI works: `codicil --version`, `codicil index <path>`, `codicil serve <path>`.
- ✅ **Graceful degradation** — with no embedding host and an empty index, `query_docs`
  returned real results via keyword fallback. Root cause double-checked, not assumed: the
  embed host was confirmed unreachable (`curl` to `localhost:11434` failed to connect) and
  the index was confirmed empty (`.codicil/index_state.json` was `{}`).
- ✅ **Live loop inside Claude Code, end-to-end** — `mcp__codicil__query_docs` and
  `mcp__codicil__reindex_docs` confirmed live and callable from a real Claude Code session,
  returning fresh results pulled straight off disk.
- ✅ **Test suite: 12 passing, fully offline** (`pytest -q`), including the headline
  invariant `test_failed_reindex_preserves_old_chunks`.
- ✅ **CI**: GitHub Actions running the test suite on `ubuntu-latest` / Python 3.11, passing
  on every merged PR so far (#1–#4).
- ✅ **Public GitHub repo**: `github.com/colehellman/codicil`, confirmed public
  (`gh repo view` → `visibility: PUBLIC`).
- ✅ **Demo GIF**: real, unedited terminal recording of `query_docs` answering a question via
  keyword fallback, embedded in README.md (`docs/demo/demo.gif`, regenerate with
  `vhs docs/demo/demo.tape`).
- ✅ **Packaging**: `python -m build` produces a clean sdist + wheel off current `main` —
  verified the sdist contains only `src/`, `tests/`, and Hatch's always-included metadata
  files (fixed a real leak of `.claude/settings.local.json`, `.mcp.json`, `CLAUDE.md`,
  `STATUS.md`, `.github/` in PR #3).
- ✅ **Published to PyPI**: `codicil 0.1.0` is live — verified via the PyPI JSON API
  (`https://pypi.org/pypi/codicil/json` returns `name: codicil`, `version: 0.1.0`), page at
  `pypi.org/project/codicil/0.1.0/`. Both the sdist and wheel passed `twine check` before
  upload. `pip install codicil` now works for anyone, not just from-source installs.
- ⚠️ Semantic path (real embeddings via remote Ollama, `nomic-embed-text`) was verified in an
  earlier session per prior notes, not re-verified since.
- ✅ **Embed-failure warning noise fixed** (PR #6) — `index_repo` used to print one identical
  "cannot reach embedding host" line per file (~16 lines on this repo's own doc count); now
  counts failures and prints one consolidated summary line, with distinct error messages kept
  (not collapsed to the last one) if failures have different causes in the same run. Verified
  end-to-end: `codicil index .` with Ollama unreachable now prints 1 warning line, not 8+.
- ✅ **README corrected to match actual behavior** (PR #7) — removed an unimplemented "optional
  git hooks re-index on commit" claim (no such code exists anywhere in the repo) and narrowed
  the "only one process is ever allowed to own the store" claim to what `_synchronized`
  (a `threading.RLock`) actually guarantees: in-process serialization only, not a cross-process
  lock.
- ✅ **Repo description and topics set** — was empty (`gh repo view` confirmed
  `description: ""`); now has a description matching README's pitch and topics
  (`mcp`, `rag`, `llm`, `claude`, `documentation`, `semantic-search`) matching
  `pyproject.toml`'s existing keywords.
- ✅ **`codicil index` summary moved to stdout** (PR #9) — it previously shared stderr with
  the embed-failure warning, so there was no way to silence the warning without also losing
  the summary. Verified end-to-end: `codicil index . 2>/dev/null` now still prints the
  summary; `codicil index . 1>/dev/null` shows only the warning.
- ✅ **Ranking-wobble mitigation validated against real embeddings** (PR #11, validated
  2026-07-07) — `query_docs` widens the candidate pool and blends embedding score with a
  keyword-overlap signal (`KEYWORD_RERANK_WEIGHT = 0.05`) before truncating to the requested
  count. Originally shipped with only synthetic-vector tests (no reachable embedding host at
  the time); since validated live with real Ollama + `nomic-embed-text` on this repo's own
  docs. Observed real effects: query *"atomic swap reindexing safety"* had a raw embedding
  gap of 0.602 vs 0.594 (CLAUDE.md over README.md) — comparable in scale to the original
  measured wobble (0.611 vs 0.598) — and reranking flipped the order to README.md first.
  Query *"how does it handle failures"* pulled STATUS.md (raw score 0.649) above two
  README.md chunks scored higher (0.662, 0.657) on keyword overlap. Confirmed known
  limitation also holds live: query *"CI setup"* reranked identically to raw order, since
  `_extract_keywords` drops `"CI"` (≤2 chars), leaving only `"setup"` as signal.
  Side discovery during validation, fixed in PR #15: `.serena/project.yml` was getting indexed
  (matched `.yml` in `INDEXED_EXTENSIONS`; `.serena` wasn't in `SKIP_DIRS`) and surfacing in
  real query results — tool metadata being treated as project documentation. Added `.serena`
  to `SKIP_DIRS`; verified fixed by rebuilding the real index (8 files/44 chunks → 6 files/37
  chunks) and re-running the same query — `.serena` no longer appears.

### Open issues (candidates for GitHub issues)
1. ~~Ranking wobble on vague/short queries~~ — mitigated and validated against real
   embeddings (see above). Known residual gap: acronym/2-char-only queries still get no
   keyword-overlap correction — acceptable tradeoff for a lightweight heuristic, not
   revisited.
2. ~~Repo metadata gap~~ — done, description + topics set (see above).
3. ~~`codicil index` UX rough edge~~ — done. Per-file warning spam consolidated (PR #6) and
   the summary moved to stdout so it's independent of the warning stream (PR #9).
4. ~~Hardcoded relevance threshold~~ — done. `CODICIL_MIN_SCORE` (default 0.5).
5. ~~grep-fallback duplicated snippet lines~~ — done, de-duplicated with regression test.
6. ~~`.serena/project.yml` gets indexed~~ — done (PR #15). Added `.serena` to `SKIP_DIRS`.

## Git
- 18 commits on `main`: `04aa7d8` (first pass) → `c327424` (threshold/dedup fix) → `7691c2e`
  (gitignore update) → `fb54d07` (setup docs + CI, PR #1) → `2ba04a6` (STATUS.md refresh,
  PR #2) → `ab93ffc` (sdist packaging fix, PR #3) → `f4a497c` (demo GIF, PR #4) → `bd37d6c`
  (STATUS.md refresh, PR #5) → `6421ce0` (embed-warning consolidation, PR #6) → `557b8e2`
  (README wording fix, PR #7) → `669d6d6` (STATUS.md refresh, PR #8) → `6bd2dca` (index
  summary to stdout, PR #9) → `2c305bc` (STATUS.md refresh, PR #10) → `d0339a6`
  (keyword-overlap reranking, PR #11) → `58fb5e3` (STATUS.md refresh, PR #12) → `d830c34`
  (STATUS.md refresh, PyPI publish, PR #13) → `e92a30f` (real-embedding rerank validation,
  PR #14) → `3860b87` (exclude .serena from indexing, PR #15).
- Remote: `origin` → `git@github.com:colehellman/codicil.git`, public, default branch `main`.
- Standing process: every change lands via branch → PR → review → fix findings → squash-merge
  → pull, no direct commits to `main` (established this session, PRs #1–#15 all followed it).
- Open branch, no PR yet: `blog-draft` — see below.

## Next steps (agreed sequence)
1. ~~Close the live Claude Code loop~~ — done, verified.
2. ~~`docs/SETUP.md`~~ — done, merged (PR #1).
3. ~~Minimal CI~~ — done, merged (PR #1), passing on Linux.
4. ~~Create the public GitHub repo~~ — already existed; confirmed public.
5. **In progress:**
   - ~~Demo GIF~~ — done, merged (PR #4).
   - **Blog post drafted, not published.** `docs/blog/the-day-my-embedding-server-died.md`
     exists on pushed branch `blog-draft` — deliberately not opened as a PR yet (this repo is
     public, so a PR would expose the draft before it's been read/approved). Waiting on
     read-through before opening the PR.
   - ~~PyPI publish~~ — done. `codicil 0.1.0` published and verified live (see above).

## Positioning (don't drift)
Sharp, differentiated, reliability-first tool + portfolio piece. The "AI memory" category is
saturated (Engram $98M + many exact-pitch clones), so **do not** frame this as a
category-defining memory platform. Wedge: reliability-first, zero-infra, doc-native. Vision
(durable engineering memory) is the *direction*, not a v1 claim.
