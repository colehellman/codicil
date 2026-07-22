"""Keyword-overlap reranking corrects close embedding-score margins.

STATUS.md documents a measured wobble with nomic-embed-text: a loosely related
doc can rank marginally above the right one (0.611 vs 0.598). This test can't
reproduce that exact real-world embedding behavior offline, but it simulates
the same shape of problem with hand-crafted vectors at those exact scores, to
verify the reranking mechanism itself works: given a close embedding-score
margin, the doc that actually contains the query's keywords should win.
"""

import math

from codicil import server


def _unit_vec(cosine_to_query: float) -> list[float]:
    """A 16-dim unit vector whose cosine similarity to [1, 0, ...] is exact."""
    return [cosine_to_query, math.sqrt(1 - cosine_to_query ** 2)] + [0.0] * 14


def test_rerank_corrects_close_embedding_margin(docs_repo, monkeypatch):
    (docs_repo / "right.md").write_text(
        "# Right\n\nExplains atomic swap reindexing safety in detail.\n"
    )
    (docs_repo / "wrong.md").write_text(
        "# Wrong\n\nUnrelated content about deployment pipelines.\n"
    )

    query_vec = [1.0] + [0.0] * 15

    def fake_embed(text, kind="query"):
        if "right.md" in text:
            return _unit_vec(0.598)  # the correct doc — deliberately lower raw score
        if "wrong.md" in text:
            return _unit_vec(0.611)  # the loosely related doc — deliberately higher
        return query_vec

    monkeypatch.setattr(server, "embed", fake_embed)
    monkeypatch.setattr(
        server, "embed_many", lambda texts: [fake_embed(t, "document") for t in texts]
    )

    server.index_repo()
    # Raw embedding order would put wrong.md first (0.611 > 0.598); reranking on
    # keyword overlap (query keywords only appear in right.md) should flip it.
    out = server.query_docs("atomic swap reindexing safety", n_results=1)["results"]
    assert "right.md" in out
    assert "wrong.md" not in out


def test_rerank_does_not_override_a_large_embedding_gap(docs_repo, monkeypatch):
    """Keyword overlap should only break close ties, not outrank a genuinely
    better semantic match — the blend weights embedding score at 0.85."""
    (docs_repo / "clear-winner.md").write_text(
        "# Clear winner\n\nThis document shares no keywords with the query at all.\n"
    )
    (docs_repo / "keyword-stuffed.md").write_text(
        "# Keyword stuffed\n\natomic swap reindexing safety atomic swap reindexing safety.\n"
    )

    query_vec = [1.0] + [0.0] * 15

    def fake_embed(text, kind="query"):
        if "clear-winner.md" in text:
            return _unit_vec(0.9)   # much better embedding match, zero keyword overlap
        if "keyword-stuffed.md" in text:
            return _unit_vec(0.55)  # weaker embedding match, full keyword overlap
        return query_vec

    monkeypatch.setattr(server, "embed", fake_embed)
    monkeypatch.setattr(
        server, "embed_many", lambda texts: [fake_embed(t, "document") for t in texts]
    )

    server.index_repo()
    out = server.query_docs("atomic swap reindexing safety", n_results=1)["results"]
    assert "clear-winner.md" in out
    assert "keyword-stuffed.md" not in out
