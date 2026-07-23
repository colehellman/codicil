"""Codicil MCP server.

Indexes a repository's documentation and exposes semantic search as an MCP tool.
Embeddings come from an Ollama-compatible endpoint. If that endpoint is unreachable,
every query degrades to a pure-Python keyword search over the same files (grep_fallback)
— an index that can't answer semantically is never a dead end.
"""

import functools
import hashlib
import json
import os
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict

import chromadb
import httpx
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Config (all env-driven; CLI sets CODICIL_REPO before importing this module)
# ---------------------------------------------------------------------------

REPO_PATH   = Path(os.environ.get("CODICIL_REPO", ".")).resolve()
STORE_PATH  = Path(os.environ.get("CODICIL_STORE", REPO_PATH / ".codicil"))
EMBED_URL   = os.environ.get("CODICIL_EMBED_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("CODICIL_EMBED_MODEL", "nomic-embed-text")
EMBED_WORKERS = int(os.environ.get("CODICIL_EMBED_WORKERS", "3"))
# nomic-embed-text is asymmetric: it expects "search_document:" on indexed text and
# "search_query:" on queries. Skipping the prefixes measurably hurts recall (a relevant
# doc can fall below the relevance threshold). Only apply them for nomic models — other
# embedders would be confused by the prefixes.
_USE_NOMIC_PREFIX = "nomic" in EMBED_MODEL.lower()

INDEXED_EXTENSIONS = {".md", ".mdx", ".rst", ".txt", ".yaml", ".yml", ".toml"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__",
             ".codicil", "dist", "build", ".mypy_cache", ".pytest_cache", ".serena"}

MAX_CHUNK = 1500   # chars per chunk
OVERLAP   = 150    # overlap between consecutive chunks
# Minimum similarity (0–1) for a passage to be returned; score = 1 - cosine_distance.
# Configurable so you can trade recall for precision without editing code. Raise it to
# return only very close matches; lower it to surface more.
MIN_SCORE = float(os.environ.get("CODICIL_MIN_SCORE", "0.5"))

# Reranking: a vague/short query can leave the right chunk just below a loosely
# related one (measured previously: 0.611 vs 0.598 — well within embedding noise).
# Widen the candidate pool past what's returned, then nudge the final order with a
# cheap keyword-overlap signal before truncating to n_results. Embedding score stays
# dominant (and is what's displayed). Keep this weight small: at 0.05, keyword
# overlap can only flip candidates whose embedding scores differ by less than
# weight/(1-weight) ≈ 0.05 — comfortably covering the measured 0.013 gap without
# letting keyword-stuffed-but-less-relevant chunks override a real quality gap.
# Known gap: _extract_keywords drops tokens ≤2 chars, so a query with no token
# longer than that (e.g. a bare acronym) gets no keyword signal at all and
# reranking becomes a no-op — falls back to pure embedding order, same as before.
RERANK_POOL_SIZE = 15
KEYWORD_RERANK_WEIGHT = 0.05

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

STORE_PATH.mkdir(parents=True, exist_ok=True)
# Keep indexes for different embedding models separate. Chroma fixes a collection's
# vector dimension on its first write, so reusing one collection across models can
# otherwise make a model change permanently unindexable.
_MODEL_KEY = hashlib.sha256(EMBED_MODEL.encode("utf-8")).hexdigest()[:12]
COLLECTION_NAME = f"docs_{_MODEL_KEY}"
STATE_FILE = STORE_PATH / f"index_state_{_MODEL_KEY}.json"
# Tracks when the semantic backend last started failing, so query_docs can report
# how long a query has been degraded instead of just that it currently is — the
# two-week embed-host outage that motivated this was invisible precisely because
# nothing recorded *when* it started. Only an actual embed() failure counts as
# "degraded" here — an empty collection (nothing indexed yet, or a repo with no
# indexable files) also serves via keyword_fallback but is a different condition
# and must not mark this, or a healthy backend on a fresh repo would falsely and
# permanently read as "degraded since <first query>".
DEGRADATION_FILE = STORE_PATH / f"degradation_{_MODEL_KEY}.json"

# Chroma's persistent client and the JSON state file are process-local resources.
# Hold an exclusive advisory lock for this server/CLI process so a hook or a second
# command cannot mutate the same store concurrently.
try:
    import fcntl
except ImportError as e:  # pragma: no cover - Codicil currently supports Unix hosts.
    raise RuntimeError("Codicil requires a Unix advisory-lock implementation.") from e

_store_lock_file = (STORE_PATH / "store.lock").open("a+")
try:
    fcntl.flock(_store_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError as e:
    raise RuntimeError(
        f"Codicil store is already in use: {STORE_PATH}. "
        "Stop the other codicil process before starting another one."
    ) from e

chroma = chromadb.PersistentClient(path=str(STORE_PATH / "chroma"))
collection = chroma.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

# The process lock above protects separate CLI/server instances. This lock serializes
# threads within the owning process and is reentrant for indexer calls from MCP tools.
_index_lock = threading.RLock()


def _synchronized(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _index_lock:
            return fn(*args, **kwargs)
    return wrapper


def is_indexed_file(path: Path) -> bool:
    return path.suffix.lower() in INDEXED_EXTENSIONS

# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

# Shared client → keep-alive connection pooling; thread-safe for embed_many().
_http = httpx.Client(
    timeout=30.0,
    limits=httpx.Limits(max_keepalive_connections=EMBED_WORKERS, max_connections=EMBED_WORKERS),
)


def embed(text: str, kind: str = "query") -> list[float]:
    """Embed `text`. `kind` is "query" or "document" — nomic models use it to pick the
    task prefix; for other models it's ignored."""
    if _USE_NOMIC_PREFIX:
        prefix = "search_document: " if kind == "document" else "search_query: "
        text = prefix + text
    try:
        r = _http.post(
            f"{EMBED_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
        )
        r.raise_for_status()
        return r.json()["embedding"]
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot reach the embedding host at {EMBED_URL}. "
            "Is it running? (Queries will fall back to keyword search.)"
        )
    except Exception as e:
        raise RuntimeError(f"Embedding error: {e}")


def embed_many(texts: list[str]) -> list[list[float]]:
    """Embed chunks concurrently, preserving order. On the first failure, cancel the
    rest and propagate so the caller skips the file fast instead of waiting out one
    connect-timeout per already-submitted chunk."""
    if len(texts) <= 1:
        return [embed(t, kind="document") for t in texts]
    ex = ThreadPoolExecutor(max_workers=min(EMBED_WORKERS, len(texts)))
    try:
        futures = [ex.submit(embed, t, "document") for t in texts]
        return [f.result() for f in futures]
    except Exception:
        ex.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        ex.shutdown(wait=False)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


# A fixed (query, document) pair with zero shared vocabulary — reachability alone
# doesn't prove the embedding backend is actually working: a wrong model, a
# corrupted response, or a silently-truncated vector would still let embed()
# return *something* without raising. Cosine similarity between a genuinely
# related pair that share no literal words is what actually exercises semantic
# understanding, not connectivity. Verified zero token overlap between these two
# strings (case-insensitive, punctuation-stripped) before choosing them.
_CANARY_QUERY = "How would someone get money back after paying out of pocket on a business trip?"
_CANARY_DOCUMENT = "Employees can submit reimbursement requests for travel expenses through the finance portal."

# ---------------------------------------------------------------------------
# Keyword fallback (used when the embedding host is offline)
# ---------------------------------------------------------------------------

# Natural-language questions (the phrasing an AI assistant actually relays) front-load
# filler words ("how", "do", "you") that pass the length>2 filter and can occupy
# keyword slots ahead of the words that actually distinguish one doc from another.
# Verified against a real external corpus (pallets/click docs): the query "How do I
# test a Click command in unit tests?" extracted ['how', 'test', 'click', 'command',
# 'unit'] via the old logic, and grep_fallback ranked an unrelated doc above the
# actually-relevant testing doc. Filtering fillers first fixes that without needing
# corpus-wide IDF weighting.
_STOPWORDS = {
    "how", "why", "what", "when", "where", "who", "which", "does", "did", "do",
    "you", "your", "the", "and", "for", "are", "but", "not", "with", "this",
    "that", "from", "have", "has", "had", "was", "were", "will", "can", "could",
    "would", "should", "into", "about", "there", "their", "them", "get", "use",
    "using",
}


def _extract_keywords(query: str) -> list[str]:
    candidates = [w.lower() for w in query.split() if len(w) > 2]
    # An all-filler query (e.g. "How do you use this for that") would otherwise filter
    # down to nothing, and grep_fallback's `if not keywords` guard (below) would then
    # skip the search entirely — worse than the pre-stopword-filter behavior. Falling
    # back to the unfiltered candidates preserves "degrade, never fail": the same
    # weak-but-nonzero keyword set the old logic would have used.
    filtered = [w for w in candidates if w not in _STOPWORDS]
    return (filtered or candidates)[:5]


def _keyword_overlap(keywords: list[str], text: str) -> float:
    """Fraction of `keywords` present in `text` (0..1). Used to nudge semantic
    reranking, not as a standalone relevance signal."""
    if not keywords:
        return 0.0
    lowered = text.lower()
    return sum(1 for kw in keywords if kw in lowered) / len(keywords)


def grep_fallback(query: str, n_results: int = 5) -> str:
    """Pure-Python keyword search over repo files when embeddings are unavailable.
    Scores each file by how many query keywords it contains, then extracts the
    best-matching lines. No index or external binary required."""
    keywords = _extract_keywords(query)
    if not keywords:
        return "No search terms provided."

    matches: list[tuple[int, str, str]] = []  # (score, rel_path, snippet)
    for path in sorted(REPO_PATH.rglob("*")):
        if path.is_dir() or any(d in path.parts for d in SKIP_DIRS):
            continue
        if not is_indexed_file(path):
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"codicil: skipping {path} in keyword search — {e}", file=sys.stderr)
            continue

        score = sum(1 for kw in keywords if kw in raw.lower())
        if score == 0:
            continue

        rel = str(path.relative_to(REPO_PATH))
        lines = raw.splitlines()
        # Collect the set of line indices to show (a window around each keyword hit).
        # Using a set de-duplicates the overlap when hits land on adjacent lines.
        include: set[int] = set()
        for i, line in enumerate(lines):
            if any(kw in line.lower() for kw in keywords):
                include.update(range(max(0, i - 1), min(len(lines), i + 4)))
            if len(include) >= 20:
                break
        picked = sorted(include)[:20]
        snippet_lines: list[str] = []
        prev = None
        for j in picked:
            if prev is not None and j > prev + 1:
                snippet_lines.append("…")  # non-contiguous region
            snippet_lines.append(lines[j])
            prev = j
        matches.append((score, rel, "\n".join(snippet_lines)))

    matches.sort(key=lambda x: x[0], reverse=True)
    matches = matches[:n_results]
    if not matches:
        return f"*keyword search — no matches for:* `{query}`"

    parts = [f"*keyword search for:* `{query}`\n"]
    for score, rel, snippet in matches:
        hits = "hit" if score == 1 else "hits"
        parts.append(f"**{rel}** ({score} keyword {hits})\n\n```\n{snippet[:600]}\n```")
    return "\n\n---\n\n".join(parts)

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_markdown(text: str) -> list[str]:
    """Split on H1/H2 headers; sub-chunk oversized sections."""
    sections: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if (line.startswith("## ") or line.startswith("# ")) and current:
            sections.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current))

    chunks: list[str] = []
    for section in sections:
        if len(section) <= MAX_CHUNK:
            chunks.append(section)
        else:
            for i in range(0, len(section), MAX_CHUNK - OVERLAP):
                chunks.append(section[i: i + MAX_CHUNK])
    return chunks


def chunk_generic(text: str) -> list[str]:
    return [text[i: i + MAX_CHUNK] for i in range(0, len(text), MAX_CHUNK - OVERLAP)]


def chunk(text: str, rel_path: str) -> list[str]:
    raw = chunk_markdown(text) if rel_path.endswith((".md", ".mdx")) else chunk_generic(text)
    # Prepend source so retrieved chunks are self-identifying inside the assistant.
    return [f"[{rel_path}]\n{c}" for c in raw if len(c.strip()) > 40]

# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


@_synchronized
def index_repo(force: bool = False) -> tuple[int, int]:
    """Index docs under REPO_PATH. Incremental by mtime. Returns (indexed, skipped)."""
    state = _load_state()
    indexed = skipped = 0
    embed_failures = 0
    embed_errors: set[str] = set()

    # Drop index entries for files that no longer exist.
    for rel in list(state.keys()):
        if not (REPO_PATH / rel).exists():
            existing = collection.get(where={"source": rel})
            if existing["ids"]:
                collection.delete(ids=existing["ids"])
            del state[rel]

    for path in sorted(REPO_PATH.rglob("*")):
        if path.is_dir() or any(d in path.parts for d in SKIP_DIRS):
            continue
        if not is_indexed_file(path):
            continue

        rel = str(path.relative_to(REPO_PATH))
        mtime = path.stat().st_mtime
        if not force and state.get(rel) == mtime:
            skipped += 1
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"codicil: skipping {path} — {e}", file=sys.stderr)
            continue
        chunks = chunk(text, rel)
        if not chunks:
            # An intentionally empty or tiny document supersedes any indexed version.
            # Record its mtime so normal incremental runs do not repeatedly process it.
            existing = collection.get(where={"source": rel})
            if existing["ids"]:
                collection.delete(ids=existing["ids"])
            state[rel] = mtime
            indexed += 1
            continue

        # Embed FIRST, then swap. Deleting a file's old chunks before a possibly
        # failing embed would wipe its entry when the embedding host is down —
        # the worst case must be stale, never empty.
        try:
            embeddings = embed_many(chunks)
        except RuntimeError as e:
            # Same failure (e.g. embed host down) usually repeats per file; report
            # once after the loop instead of flooding stderr with identical lines.
            # Distinct messages are kept (not just the last one) so a mid-run
            # change in failure cause isn't silently discarded.
            embed_failures += 1
            embed_errors.add(str(e))
            skipped += 1
            continue

        # Add a new generation before deleting the old one. `collection.add()` can
        # fail after embedding (for example, disk or schema errors); retaining the
        # old generation preserves the reliability invariant in that case too.
        existing = collection.get(where={"source": rel})
        old_ids = existing["ids"]
        generation = uuid.uuid4().hex
        collection.add(
            ids=[f"{rel}::{generation}::{i}" for i in range(len(chunks))],
            embeddings=embeddings,
            documents=chunks,
            metadatas=[{"source": rel, "chunk": i} for i in range(len(chunks))],
        )
        if old_ids:
            collection.delete(ids=old_ids)
        state[rel] = mtime
        indexed += 1

    if embed_failures:
        reasons = "; ".join(sorted(embed_errors))
        print(f"codicil: {embed_failures} file(s) skipped — {reasons}", file=sys.stderr)

    _save_state(state)
    return indexed, skipped

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("codicil")


class QueryResult(TypedDict):
    """query_docs's structured return. `backend` and `degraded_since` are here so
    a calling assistant can detect and surface degradation programmatically instead
    of relying on prose it might paraphrase away — see the module docstring."""
    backend: Literal["semantic", "keyword_fallback"]
    degraded_since: str | None  # ISO 8601 UTC timestamp; None while backend == "semantic"
    results: str


def _load_degradation() -> dict:
    return json.loads(DEGRADATION_FILE.read_text()) if DEGRADATION_FILE.exists() else {}


def _mark_healthy(strong: bool = False) -> None:
    """Clear degradation. query_docs's plain "embed() didn't raise" signal (the
    default, `strong=False`) is weaker than codicil_status's canary check — it
    never verifies embedding *quality*, only reachability — so it must not clear
    a degradation the canary flagged: a corrupted-but-reachable model can still
    let ordinary queries succeed while remaining genuinely untrustworthy, and
    clearing that would reset degraded_since to "now" on the next canary check
    instead of preserving the true onset. Only codicil_status's canary-validated
    success (`strong=True`) can clear a canary-flagged degradation.
    """
    state = _load_degradation()
    if state.get("degraded_since") is None:
        return
    if not strong and state.get("reason") == "canary":
        return
    DEGRADATION_FILE.write_text(json.dumps({"degraded_since": None, "reason": None}))


def _mark_degraded(reason: Literal["connectivity", "canary"] = "connectivity") -> str | None:
    """Record the first time degradation was observed; return that timestamp
    unchanged on subsequent calls so `degraded_since` reflects onset, not now."""
    state = _load_degradation()
    if state.get("degraded_since") is None:
        state["degraded_since"] = datetime.now(timezone.utc).isoformat()
        state["reason"] = reason
        DEGRADATION_FILE.write_text(json.dumps(state))
    return state["degraded_since"]


@mcp.tool()
@_synchronized
def query_docs(query: str, n_results: int = 5) -> QueryResult:
    """Search this repository's documentation and return the relevant passages.

    Use this before reading whole files — it returns only the chunks that matter,
    at a fraction of the token cost. Falls back to keyword search if the embedding
    host is offline; check `backend` in the response to see which one answered.

    Args:
        query:     Natural-language question or keywords.
        n_results: Passages to return, 1–10 (default 5).
    """
    if collection.count() == 0:
        # Nothing indexed yet (fresh repo, or one with no indexable files) — keyword
        # search is genuinely what serves this query, but that's not evidence the
        # embedding backend itself has failed, so don't mark degradation for it.
        return QueryResult(
            backend="keyword_fallback",
            degraded_since=None,
            results=grep_fallback(query, n_results),
        )
    try:
        q_vec = embed(query)
    except RuntimeError:
        return QueryResult(
            backend="keyword_fallback",
            degraded_since=_mark_degraded(),
            results=grep_fallback(query, n_results),
        )
    _mark_healthy()

    n = min(max(n_results, 1), 10, collection.count())
    # n is capped at 10 (above) and RERANK_POOL_SIZE is 15, so the pool always
    # widens to RERANK_POOL_SIZE — no need to max() against n.
    pool = min(RERANK_POOL_SIZE, collection.count())
    results = collection.query(
        query_embeddings=[q_vec],
        n_results=pool,
        include=["documents", "metadatas", "distances"],
    )
    if not results["documents"][0]:
        return QueryResult(backend="semantic", degraded_since=None, results="No relevant documentation found.")

    keywords = _extract_keywords(query)
    candidates = []  # (rerank_score, embed_score, doc, meta)
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        embed_score = round(1 - dist, 3)
        if embed_score < MIN_SCORE:
            continue
        overlap = _keyword_overlap(keywords, doc)
        rerank_score = (1 - KEYWORD_RERANK_WEIGHT) * embed_score + KEYWORD_RERANK_WEIGHT * overlap
        candidates.append((rerank_score, embed_score, doc, meta))
    if not candidates:
        return QueryResult(
            backend="semantic", degraded_since=None,
            results="No sufficiently relevant documentation found.",
        )

    # Rerank the wider pool by the blended score, then keep only the originally
    # requested count. The displayed score is still the raw embedding similarity —
    # the blend only decides order, so CODICIL_MIN_SCORE's documented meaning
    # (embedding similarity) doesn't change.
    candidates.sort(key=lambda c: c[0], reverse=True)
    parts = [
        f"**{meta['source']}** (score {embed_score})\n\n{doc}"
        for _, embed_score, doc, meta in candidates[:n]
    ]
    return QueryResult(backend="semantic", degraded_since=None, results="\n\n---\n\n".join(parts))


@mcp.tool()
@_synchronized
def reindex_docs(force: bool = False) -> str:
    """Rebuild the documentation index. Incremental by default (only changed files)."""
    try:
        indexed, skipped = index_repo(force=force)
    except RuntimeError as e:
        return str(e)
    return f"{indexed} indexed, {skipped} skipped ({collection.count()} total chunks)."


class StatusResult(TypedDict):
    """codicil_status's structured return — check health on demand instead of
    waiting for a real query to reveal degradation."""
    backend: Literal["semantic", "keyword_fallback"]
    degraded_since: str | None
    canary_ok: bool  # a fixed no-lexical-overlap (query, doc) pair actually scores as related
    canary_score: float | None  # None if the embed host was unreachable
    embed_url: str
    embed_model: str
    indexed_files: int
    indexed_chunks: int
    stale_files: int  # on disk but not reflected in the index: changed, new, or deleted


@mcp.tool()
def codicil_status() -> StatusResult:
    """Check whether semantic search is actually reachable right now, and how
    stale the index is — without waiting for a real query to reveal degradation.

    Unlike query_docs, this always attempts to reach the embedding host: that's
    the point of a status check. It does not reindex or write chunks.
    """
    # Deliberately NOT under _index_lock: embed() can block for the full 30s
    # client timeout against a slow/unresponsive host, and this tool's only job
    # is a quick health probe — holding the lock here would stall every other
    # in-process query_docs/reindex_docs call (including query_docs's fast,
    # network-free keyword fallback) for that same window. Only the bookkeeping
    # below, which touches shared state, needs the lock.
    # Connectivity alone doesn't prove the backend is trustworthy: a wrong model,
    # a corrupted response, or a silently-truncated vector would still let embed()
    # return *something* without raising. The canary must also score as related —
    # a low score despite a successful embed() call counts as degraded too, since
    # query_docs's real answers would be equally corrupted by the same cause.
    degrade_reason: Literal["connectivity", "canary"] = "connectivity"
    try:
        query_vec = embed(_CANARY_QUERY, kind="query")
        doc_vec = embed(_CANARY_DOCUMENT, kind="document")
        canary_score: float | None = round(_cosine_similarity(query_vec, doc_vec), 3)
        canary_ok = canary_score >= MIN_SCORE
        degrade_reason = "canary"  # embed reached the host fine; only the canary failed
    except RuntimeError:
        canary_score = None
        canary_ok = False

    healthy = canary_ok
    backend: Literal["semantic", "keyword_fallback"] = "semantic" if healthy else "keyword_fallback"

    with _index_lock:
        if healthy:
            _mark_healthy(strong=True)
            degraded_since = None
        else:
            degraded_since = _mark_degraded(degrade_reason)

        state = _load_state()
        stale = sum(
            1 for rel in state if not (REPO_PATH / rel).exists()
        )
        for path in sorted(REPO_PATH.rglob("*")):
            if path.is_dir() or any(d in path.parts for d in SKIP_DIRS) or not is_indexed_file(path):
                continue
            rel = str(path.relative_to(REPO_PATH))
            if state.get(rel) != path.stat().st_mtime:
                stale += 1

        return StatusResult(
            backend=backend,
            degraded_since=degraded_since,
            canary_ok=canary_ok,
            canary_score=canary_score,
            embed_url=EMBED_URL,
            embed_model=EMBED_MODEL,
            indexed_files=len(state),
            indexed_chunks=collection.count(),
            stale_files=stale,
        )


def serve() -> None:
    """Build the index if empty, then run the MCP server (called by `codicil serve`)."""
    if collection.count() == 0:
        print(f"codicil: index empty — building from {REPO_PATH} …", file=sys.stderr)
        try:
            indexed, _ = index_repo()
            print(f"codicil: indexed {indexed} files ({collection.count()} chunks).", file=sys.stderr)
        except RuntimeError as e:
            print(f"codicil: could not build index ({e}); queries will use keyword search.", file=sys.stderr)
    mcp.run()
