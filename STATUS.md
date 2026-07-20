# Codicil — Status & Handoff

_Last updated: 2026-07-20. This is a working handoff note, not marketing — see `README.md` for the product guide._

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
  returning fresh results pulled straight off disk (verified by seeing files created *during
  the session itself* show up in a query result — proves it's reading current state, not a
  stale or mocked index).
- ✅ **Test suite: 21 passing, fully offline** (`pytest -q`), including regressions for
  embed/write-safe swaps, empty-file removal, and cross-process store ownership.
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
- ✅ **Published to PyPI, twice.** `codicil 0.1.0` (PR #13) was the only release for 9 PRs
  (#14–#22) — `main` had since gained the real cross-process guard, per-model collection
  isolation, keyword-overlap reranking, and the `codicil query` subcommand, none of which
  `pip install codicil` actually shipped. `codicil 0.2.0` (2026-07-20) closes that gap —
  verified live via the version-specific JSON API (`https://pypi.org/pypi/codicil/0.2.0/json`
  returns `version: 0.2.0`, `requires_python: >=3.11`), page at
  `pypi.org/project/codicil/0.2.0/`. (The top-level "latest" endpoint,
  `pypi.org/pypi/codicil/json`, lagged a few seconds behind the real release — CDN cache
  propagation, not a failed upload; the version-specific endpoint confirmed it immediately.)
  Both the sdist and wheel passed `twine check` before upload.
- ⚠️ Semantic path (real embeddings via remote Ollama, `nomic-embed-text`) was verified in an
  earlier session per prior notes, not re-verified since.
- ✅ **`__version__` found out of sync with `pyproject.toml`** — `cli.py`'s `--version` flag
  reads `codicil.__version__` (`src/codicil/__init__.py`), which isn't wired to
  `pyproject.toml` at all. The 0.2.0 bump initially only touched `pyproject.toml`, so
  `codicil --version` kept reporting `0.1.0` until a follow-up commit on the same PR fixed
  `__init__.py` too. Worth remembering for the next release: bump both, or wire
  `__version__` to read from installed package metadata instead of duplicating the literal.
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
- ✅ **README credibility badges added** (PR #19) — Tests (CI), PyPI version, and MIT
  license badges under the title. Verified each resolves to a real, correct-state target
  before merging: the Tests badge SVG returns `200`/`image/svg+xml` and reflects the passing
  workflow, the PyPI badge renders `v0.1.0`, the license badge renders `MIT`, and both link
  targets (workflow page, PyPI project page) return `200`.
- ✅ **Cross-process store-access guard added, then hardened.** `_index_lock` only serializes
  access *within* one process; a separate `codicil index`/`codicil query` racing an
  already-running `codicil serve` against the same store could crash it (the same failure
  mode that hit the bespoke predecessor this project was extracted from). PR #20 shipped a
  PID-file check (`PID_FILE`, `refuse_if_server_running`) as the cross-process counterpart —
  this bullet previously said that was an `fcntl.flock` guard; it wasn't yet, that was
  premature. PR #22 replaced the PID-file check with the real thing: an exclusive
  `fcntl.flock` held for the lifetime of the owning process, so a second `serve`, `index`, or
  `query` process is refused before it can open Chroma at all, no stale-PID cleanup needed.
  Also in #22: each embedding model now gets its own Chroma collection and state file
  (`docs_<model-hash>`, `index_state_<model-hash>.json`) — Chroma fixes a collection's vector
  dimension on first write, so switching models against one shared collection could otherwise
  make the store permanently unindexable.
- ⚠️ **Blog draft merged into `main`, but still unreviewed.**
  `docs/blog/the-day-my-embedding-server-died.md` landed via PR #22 (2026-07-16) as part of a
  larger hardening PR — it wasn't opened as its own PR the way the earlier plan intended. The
  file itself still opens with "Draft — not yet published anywhere. Written for review before
  it goes out." That's still true in the sense that it isn't posted anywhere external, but
  it's now sitting readable on the public repo's default branch, which is more exposure than
  "unopened PR on a side branch." Not resolved by this refresh — needs an actual read-through
  to either drop the disclaimer or pull it back out.

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
7. ~~Cross-process concurrent access to the Chroma store~~ — done, in two steps: PR #20's
   PID-file check, then PR #22's `fcntl.flock` replacement (see Verified section above). The
   flock supplements `_synchronized`, which continues to provide only in-process serialization.
8. **New (2026-07-20): PyPI release drift.** `main` moved 9 PRs past the last publish before
   anyone caught it (see the 0.2.0 entry above). No process fix yet — no CI step, no
   reminder — flagged here so the next "should I publish" moment has something to check
   against instead of relying on memory.

## Git
- 26 commits on `main`: `04aa7d8` (first pass) → `c327424` (threshold/dedup fix) → `7691c2e`
  (gitignore update) → `fb54d07` (setup docs + CI, PR #1) → `2ba04a6` (STATUS.md refresh,
  PR #2) → `ab93ffc` (sdist packaging fix, PR #3) → `f4a497c` (demo GIF, PR #4) → `bd37d6c`
  (STATUS.md refresh, PR #5) → `6421ce0` (embed-warning consolidation, PR #6) → `557b8e2`
  (README wording fix, PR #7) → `669d6d6` (STATUS.md refresh, PR #8) → `6bd2dca` (index
  summary to stdout, PR #9) → `2c305bc` (STATUS.md refresh, PR #10) → `d0339a6`
  (keyword-overlap reranking, PR #11) → `58fb5e3` (STATUS.md refresh, PR #12) → `d830c34`
  (STATUS.md refresh, PyPI publish, PR #13) → `e92a30f` (real-embedding rerank validation,
  PR #14) → `3860b87` (exclude .serena from indexing, PR #15) → `4e552f7` (STATUS.md
  refresh, PR #16) → `4e4941f` (pip-install path in SETUP.md, PR #17) → `2a17ec7` (`codicil
  query` CLI subcommand, PR #18) → `a67242f` (README badges, PR #19) → `a334a0a`
  (cross-process store guard, PR #20) → `68eabbd` (STATUS.md refresh, PR #21) → `88b855a`
  (harden indexing: real `fcntl.flock` guard, per-model collection isolation, blog draft
  merged, PR #22) → `0d0efff` (version bump to 0.2.0, PR #23).
- Remote: `origin` → `git@github.com:colehellman/codicil.git`, public, default branch `main`.
- Standing process: every change lands via branch → PR → review → fix findings → squash-merge
  → pull, no direct commits to `main` (established this session, PRs #1–#23 all followed it).
- Branch cleanup (2026-07-20): `blog-draft` and `fix/reliability-and-docs` deleted, both
  locally and on `origin`, after confirming neither had anything `main` didn't already have.
  `blog-draft`'s copy of the blog post was an older, since-corrected draft (still said
  "PID-file check" where `main`'s post-#22 version correctly says "advisory lock");
  `fix/reliability-and-docs` was the branch squash-merged into #22 and only differed from
  `main` by the version string. Repo has a single branch, `main`, going into the
  mcpservers.org submission.

## Next steps (agreed sequence)
1. ~~Close the live Claude Code loop~~ — done, verified.
2. ~~`docs/SETUP.md`~~ — done, merged (PR #1).
3. ~~Minimal CI~~ — done, merged (PR #1), passing on Linux.
4. ~~Create the public GitHub repo~~ — already existed; confirmed public.
5. **In progress:**
   - ~~Demo GIF~~ — done, merged (PR #4).
   - **Blog post merged into `main`, still not reviewed.** Landed via PR #22 (2026-07-16) as
     part of a larger hardening PR rather than on its own — the "don't open a PR until it's
     read" plan got bypassed, not followed. Still carries its own "Draft — not yet published
     anywhere" disclaimer. Not published externally, but now readable on the public repo's
     default branch, which is more exposure than the old plan intended. Needs a read-through.
   - ~~PyPI publish~~ — done, twice. `codicil 0.1.0` (PR #13) drifted 9 PRs behind `main`
     before anyone noticed; `codicil 0.2.0` (2026-07-20) caught it up and is verified live —
     see above.
6. **Next:** submit to the mcpservers.org directory. Repo is otherwise ready — CI green,
   PyPI matches `main`, sdist/wheel verified clean, stale branches gone. The blog-draft
   disclaimer above is the one loose end worth resolving first, since directory traffic will
   land directly on this branch.

## Positioning (don't drift)
Sharp, differentiated, reliability-first tool + portfolio piece. The "AI memory" category is
saturated (Engram $98M + many exact-pitch clones), so **do not** frame this as a
category-defining memory platform. Wedge: reliability-first, zero-infra, doc-native. Vision
(durable engineering memory) is the *direction*, not a v1 claim.
