"""codicil_status checks health on demand, without waiting for a real query
to reveal degradation — unlike query_docs, it always probes the embedding host.
"""

import time

from codicil import server


def test_status_reports_semantic_when_embed_host_reachable(docs_repo, fake_embed):
    result = server.codicil_status()
    assert result["backend"] == "semantic"
    assert result["degraded_since"] is None


def test_status_reports_keyword_fallback_when_embed_host_unreachable(docs_repo, monkeypatch):
    def broken_embed(text, kind="query"):
        raise RuntimeError("cannot reach embedding host")

    monkeypatch.setattr(server, "embed", broken_embed)
    result = server.codicil_status()
    assert result["backend"] == "keyword_fallback"
    assert result["degraded_since"] is not None


def test_status_reports_embed_url_and_model(docs_repo, fake_embed):
    result = server.codicil_status()
    assert result["embed_url"] == server.EMBED_URL
    assert result["embed_model"] == server.EMBED_MODEL


def test_status_reports_indexed_counts(docs_repo, fake_embed):
    (docs_repo / "a.md").write_text("# A\n\nSome content long enough to survive chunking.\n")
    (docs_repo / "b.md").write_text("# B\n\nMore content long enough to survive chunking.\n")
    server.index_repo()

    result = server.codicil_status()
    assert result["indexed_files"] == 2
    assert result["indexed_chunks"] == server.collection.count()
    assert result["stale_files"] == 0


def test_status_counts_a_changed_file_as_stale(docs_repo, fake_embed):
    doc = docs_repo / "a.md"
    doc.write_text("# A\n\nOriginal content long enough to survive chunking.\n")
    server.index_repo()
    assert server.codicil_status()["stale_files"] == 0

    time.sleep(0.01)
    doc.write_text("# A\n\nEdited content long enough to survive chunking, now different.\n")
    result = server.codicil_status()
    assert result["stale_files"] == 1


def test_status_counts_a_deleted_file_as_stale(docs_repo, fake_embed):
    doc = docs_repo / "a.md"
    doc.write_text("# A\n\nOriginal content long enough to survive chunking.\n")
    server.index_repo()
    assert server.codicil_status()["stale_files"] == 0

    doc.unlink()
    result = server.codicil_status()
    assert result["stale_files"] == 1


def test_status_does_not_reindex_or_write_chunks(docs_repo, fake_embed):
    (docs_repo / "a.md").write_text("# A\n\nSome content long enough to survive chunking.\n")
    assert server.collection.count() == 0

    server.codicil_status()
    assert server.collection.count() == 0  # status must not index as a side effect
