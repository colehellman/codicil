"""query_docs reports which backend served each request, and how long the
semantic backend has been down — the two-week outage that motivated this was
invisible precisely because nothing recorded which backend answered or when
degradation started.
"""

from codicil import server


def test_reports_semantic_backend_when_healthy(docs_repo, fake_embed):
    (docs_repo / "a.md").write_text("# Widgets\n\nContent about widgets and gadgets.\n")
    server.index_repo()

    result = server.query_docs("widgets")
    assert result["backend"] == "semantic"
    assert result["degraded_since"] is None
    assert "a.md" in result["results"]


def test_empty_collection_uses_keyword_fallback_but_is_not_marked_degraded(docs_repo):
    # A fresh, never-indexed repo (or one with no indexable files) has to answer via
    # keyword search, but that alone is no evidence the embedding backend has failed —
    # a healthy host that's just never been asked to index anything isn't "degraded".
    (docs_repo / "a.md").write_text("# Widgets\n\nContent about widgets and gadgets.\n")
    assert server.collection.count() == 0

    result = server.query_docs("widgets")
    assert result["backend"] == "keyword_fallback"
    assert result["degraded_since"] is None
    assert "a.md" in result["results"]


def test_reports_keyword_fallback_when_embed_host_unreachable(docs_repo, fake_embed, monkeypatch):
    (docs_repo / "a.md").write_text("# Widgets\n\nContent about widgets and gadgets.\n")
    server.index_repo()  # indexed successfully while embed() still worked

    def broken_embed(text, kind="query"):
        raise RuntimeError("cannot reach embedding host")

    monkeypatch.setattr(server, "embed", broken_embed)
    result = server.query_docs("widgets")
    assert result["backend"] == "keyword_fallback"
    assert result["degraded_since"] is not None
    assert "a.md" in result["results"]


def test_degraded_since_is_stable_across_repeated_failures(docs_repo, fake_embed, monkeypatch):
    (docs_repo / "a.md").write_text("# Widgets\n\nContent about widgets and gadgets.\n")
    server.index_repo()

    def broken_embed(text, kind="query"):
        raise RuntimeError("cannot reach embedding host")

    monkeypatch.setattr(server, "embed", broken_embed)
    first = server.query_docs("widgets")["degraded_since"]
    second = server.query_docs("widgets")["degraded_since"]
    assert first == second  # onset timestamp, not "now" on every call


def test_degraded_since_clears_once_semantic_backend_recovers(docs_repo, fake_embed, monkeypatch):
    (docs_repo / "a.md").write_text("# Widgets\n\nContent about widgets and gadgets.\n")
    server.index_repo()

    def broken_embed(text, kind="query"):
        raise RuntimeError("cannot reach embedding host")

    monkeypatch.setattr(server, "embed", broken_embed)
    assert server.query_docs("widgets")["degraded_since"] is not None  # embed host down: degraded

    # Backend recovers — re-patch to a working embed (content doesn't matter here,
    # only that it succeeds instead of raising).
    monkeypatch.setattr(server, "embed", lambda text, kind="query": [0.1] * 16)
    result = server.query_docs("widgets")
    assert result["backend"] == "semantic"
    assert result["degraded_since"] is None
