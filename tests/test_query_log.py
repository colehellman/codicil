"""query_docs appends one line per call to QUERY_LOG_FILE -- a lightweight
history of real query traffic distinct from DEGRADATION_FILE's binary
onset/clearing tracking, so a slow quality decline (top_score trending down)
is visible even when nothing ever hard-fails.
"""

import json

from codicil import server


def _read_log_lines():
    if not server.QUERY_LOG_FILE.exists():
        return []
    return [json.loads(line) for line in server.QUERY_LOG_FILE.read_text().splitlines()]


def test_logs_one_line_per_query(docs_repo, fake_embed):
    (docs_repo / "a.md").write_text("# A\n\nSome content long enough to survive chunking.\n")
    server.index_repo()

    server.query_docs("widgets")
    server.query_docs("widgets")

    lines = _read_log_lines()
    assert len(lines) == 2


def test_logs_semantic_backend_with_top_score(docs_repo, fake_embed):
    (docs_repo / "a.md").write_text("# Widgets\n\nContent about widgets and gadgets.\n")
    server.index_repo()

    server.query_docs("widgets")

    lines = _read_log_lines()
    assert lines[-1]["backend"] == "semantic"
    assert isinstance(lines[-1]["top_score"], float)
    assert "ts" in lines[-1]


def test_logs_keyword_fallback_with_null_top_score_on_empty_collection(docs_repo):
    (docs_repo / "a.md").write_text("# A\n\nSome content long enough to survive chunking.\n")

    server.query_docs("anything")

    lines = _read_log_lines()
    assert lines[-1]["backend"] == "keyword_fallback"
    assert lines[-1]["top_score"] is None


def test_logs_keyword_fallback_with_null_top_score_on_embed_failure(docs_repo, fake_embed, monkeypatch):
    (docs_repo / "a.md").write_text("# A\n\nSome content long enough to survive chunking.\n")
    server.index_repo()

    def broken_embed(text, kind="query"):
        raise RuntimeError("cannot reach embedding host")

    monkeypatch.setattr(server, "embed", broken_embed)
    server.query_docs("anything")

    lines = _read_log_lines()
    assert lines[-1]["backend"] == "keyword_fallback"
    assert lines[-1]["top_score"] is None


def test_logs_best_pool_score_even_when_below_min_score(docs_repo, monkeypatch):
    # A "no sufficiently relevant" outcome still logs the best available raw
    # score -- a slow quality decline should show up as a falling top_score,
    # not just a binary found/not-found signal.
    (docs_repo / "a.md").write_text("# A\n\nSome content long enough to survive chunking.\n")

    def low_score_embed(text, kind="query"):
        return [1.0] + [0.0] * 15  # index and query vectors are orthogonal below

    monkeypatch.setattr(server, "embed", low_score_embed)
    monkeypatch.setattr(server, "embed_many", lambda texts: [[0.0] * 15 + [1.0] for _ in texts])
    server.index_repo()

    result = server.query_docs("a")
    assert "No sufficiently relevant" in result["results"]

    lines = _read_log_lines()
    assert lines[-1]["backend"] == "semantic"
    assert lines[-1]["top_score"] is not None
    assert lines[-1]["top_score"] < server.MIN_SCORE


def test_codicil_status_does_not_write_to_the_query_log(docs_repo, fake_embed):
    # Synthetic canary traffic must not muddy a log meant to reflect real usage.
    server.codicil_status()
    assert _read_log_lines() == []
