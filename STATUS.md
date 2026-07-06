# Codicil — Status & Handoff

_Last updated: 2026-07-06. This is a working handoff note, not marketing — see `README.md` for the pitch._

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
  `STATUS.md`, `.github/` in PR #3). **Not yet uploaded to PyPI** — build-only so far.
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
- ⚠️ **Ranking-wobble mitigated, not fully validated** (PR #11) — `query_docs` had no
  reranking step at all; now widens the candidate pool and blends embedding score with a
  keyword-overlap signal (`KEYWORD_RERANK_WEIGHT = 0.05`) before truncating to the requested
  count. Two regression tests with hand-crafted vectors confirm the mechanism: it corrects
  the exact measured margin (0.598 vs 0.611) and doesn't override a genuinely larger
  embedding-score gap (0.9 vs 0.55). **Not verified against the real measured wobble** — no
  reachable embedding host in this environment, and the test suite's `fake_vec` fixture is a
  hash with no semantic meaning. Also a no-op for queries with no token longer than 2 chars
  (e.g. a bare acronym) — `_extract_keywords` yields no keyword signal in that case.

### Open issues (candidates for GitHub issues)
1. ~~Ranking wobble on vague/short queries~~ — mitigated (PR #11, see above), but not
   verified against a real embedding host. Revisit if the wobble still shows up in practice.
2. ~~Repo metadata gap~~ — done, description + topics set (see above).
3. ~~`codicil index` UX rough edge~~ — done. Per-file warning spam consolidated (PR #6) and
   the summary moved to stdout so it's independent of the warning stream (PR #9).
4. ~~Hardcoded relevance threshold~~ — done. `CODICIL_MIN_SCORE` (default 0.5).
5. ~~grep-fallback duplicated snippet lines~~ — done, de-duplicated with regression test.

## Git
- 14 commits on `main`: `04aa7d8` (first pass) → `c327424` (threshold/dedup fix) → `7691c2e`
  (gitignore update) → `fb54d07` (setup docs + CI, PR #1) → `2ba04a6` (STATUS.md refresh,
  PR #2) → `ab93ffc` (sdist packaging fix, PR #3) → `f4a497c` (demo GIF, PR #4) → `bd37d6c`
  (STATUS.md refresh, PR #5) → `6421ce0` (embed-warning consolidation, PR #6) → `557b8e2`
  (README wording fix, PR #7) → `669d6d6` (STATUS.md refresh, PR #8) → `6bd2dca` (index
  summary to stdout, PR #9) → `2c305bc` (STATUS.md refresh, PR #10) → `d0339a6`
  (keyword-overlap reranking, PR #11).
- Remote: `origin` → `git@github.com:colehellman/codicil.git`, public, default branch `main`.
- Standing process: every change lands via branch → PR → review → fix findings → squash-merge
  → pull, no direct commits to `main` (established this session, PRs #1–#11 all followed it).
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
   - **PyPI publish not done.** Build-only verified (see above) — actual upload needs a PyPI
     API token and explicit go-ahead; name `codicil` was checked available in an earlier
     session (404 on the JSON API), not re-verified since.

## Positioning (don't drift)
Sharp, differentiated, reliability-first tool + portfolio piece. The "AI memory" category is
saturated (Engram $98M + many exact-pitch clones), so **do not** frame this as a
category-defining memory platform. Wedge: reliability-first, zero-infra, doc-native. Vision
(durable engineering memory) is the *direction*, not a v1 claim.
