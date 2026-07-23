"""A keyword-fallback response includes a plain-text suggestion to run
codicil_status -- structured backend/degraded_since fields exist so an
assistant can detect degradation programmatically, but nothing forces it to
act on them. This appends the next step directly into the passage content
itself, the one thing every caller reads.
"""

from codicil import server


def test_nudge_appears_when_collection_is_empty(docs_repo):
    (docs_repo / "a.md").write_text("# A\n\nSome content long enough to survive chunking.\n")
    result = server.query_docs("anything")
    assert "codicil_status" in result["results"]


def test_nudge_appears_when_embed_host_unreachable(docs_repo, fake_embed, monkeypatch):
    (docs_repo / "a.md").write_text("# A\n\nSome content long enough to survive chunking.\n")
    server.index_repo()

    def broken_embed(text, kind="query"):
        raise RuntimeError("cannot reach embedding host")

    monkeypatch.setattr(server, "embed", broken_embed)
    result = server.query_docs("anything")
    assert "codicil_status" in result["results"]


def test_nudge_absent_on_healthy_semantic_response(docs_repo, fake_embed):
    (docs_repo / "a.md").write_text("# Widgets\n\nContent about widgets and gadgets.\n")
    server.index_repo()

    result = server.query_docs("widgets")
    assert result["backend"] == "semantic"
    assert "codicil_status" not in result["results"]
