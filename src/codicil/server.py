"""Codicil MCP server.

Indexes a repository's documentation and exposes semantic search as an MCP tool.
Embeddings come from an Ollama-compatible endpoint. If that endpoint is unreachable,
every query degrades to a pure-Python keyword search over the same files (grep_fallback)
— an index that can't answer semantically is never a dead end.
"""

import functools
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
             ".codicil", "dist", "build", ".mypy_cache", ".pytest_cache"}

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
# dominant (and is what's displayed) — this only breaks close ties, it isn't a
# full reranker.
RERANK_POOL_SIZE = 15
KEYWORD_RERANK_WEIGHT = 0.15

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

STORE_PATH.mkdir(parents=True, exist_ok=True)
STATE_FILE = STORE_PATH / "index_state.json"

chroma = chromadb.PersistentClient(path=str(STORE_PATH / "chroma"))
collection = chroma.get_or_create_collection("docs", metadata={"hnsw:space": "cosine"})

# ChromaDB's PersistentClient is not safe for concurrent access — a single reentrant
# lock serializes every index write and every query so a live query never races a
# reindex. Reentrant so a synchronized query tool can call a synchronized indexer.
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

# ---------------------------------------------------------------------------
# Keyword fallback (used when the embedding host is offline)
# ---------------------------------------------------------------------------

def _extract_keywords(query: str) -> list[str]:
    return [w.lower() for w in query.split() if len(w) > 2][:5]


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
        if not text.strip():
            continue

        chunks = chunk(text, rel)
        if not chunks:
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

        existing = collection.get(where={"source": rel})
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
        collection.add(
            ids=[f"{rel}::{i}" for i in range(len(chunks))],
            embeddings=embeddings,
            documents=chunks,
            metadatas=[{"source": rel, "chunk": i} for i in range(len(chunks))],
        )
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


@mcp.tool()
@_synchronized
def query_docs(query: str, n_results: int = 5) -> str:
    """Search this repository's documentation and return the relevant passages.

    Use this before reading whole files — it returns only the chunks that matter,
    at a fraction of the token cost. Falls back to keyword search if the embedding
    host is offline.

    Args:
        query:     Natural-language question or keywords.
        n_results: Passages to return, 1–10 (default 5).
    """
    if collection.count() == 0:
        return grep_fallback(query, n_results)
    try:
        q_vec = embed(query)
    except RuntimeError:
        return grep_fallback(query, n_results)

    n = min(max(n_results, 1), 10, collection.count())
    pool = min(max(n, RERANK_POOL_SIZE), collection.count())
    results = collection.query(
        query_embeddings=[q_vec],
        n_results=pool,
        include=["documents", "metadatas", "distances"],
    )
    if not results["documents"][0]:
        return "No relevant documentation found."

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
        return "No sufficiently relevant documentation found."

    # Rerank the wider pool by the blended score, then keep only the originally
    # requested count. The displayed score is still the raw embedding similarity —
    # the blend only decides order, so CODICIL_MIN_SCORE's documented meaning
    # (embedding similarity) doesn't change.
    candidates.sort(key=lambda c: c[0], reverse=True)
    parts = [
        f"**{meta['source']}** (score {embed_score})\n\n{doc}"
        for _, embed_score, doc, meta in candidates[:n]
    ]
    return "\n\n---\n\n".join(parts)


@mcp.tool()
@_synchronized
def reindex_docs(force: bool = False) -> str:
    """Rebuild the documentation index. Incremental by default (only changed files)."""
    try:
        indexed, skipped = index_repo(force=force)
    except RuntimeError as e:
        return str(e)
    return f"{indexed} indexed, {skipped} skipped ({collection.count()} total chunks)."


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
