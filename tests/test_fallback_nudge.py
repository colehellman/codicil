"""A keyword-fallback response includes a plain-text next step -- structured
backend/degraded_since fields exist so an assistant can detect degradation
programmatically, but nothing forces it to act on them. This appends a note
directly into the passage content itself, the one thing every caller reads.

Two distinct messages, not one: an unindexed-but-healthy repo is not an
outage, and claiming "unavailable" there would reintroduce the exact false
alarm degraded_since=None was built to prevent. Neither message names a
specific command -- codicil_status is an MCP tool only, and this text is
also read verbatim by `codicil query`'s CLI output, which has no such
subcommand.
"""

from codicil import server


def test_nudge_says_not_indexed_yet_when_collection_is_empty(docs_repo):
    (docs_repo / "a.md").write_text("# A\n\nSome content long enough to survive chunking.\n")
    result = server.query_docs("anything")
    assert result["degraded_since"] is None
    assert "No semantic index exists yet" in result["results"]
    assert "unavailable" not in result["results"]  # not an outage -- don't claim one


def test_nudge_says_unavailable_when_embed_host_unreachable(docs_repo, fake_embed, monkeypatch):
    (docs_repo / "a.md").write_text("# A\n\nSome content long enough to survive chunking.\n")
    server.index_repo()

    def broken_embed(text, kind="query"):
        raise RuntimeError("cannot reach embedding host")

    monkeypatch.setattr(server, "embed", broken_embed)
    result = server.query_docs("anything")
    assert result["degraded_since"] is not None
    assert "Semantic search is currently unavailable" in result["results"]


def test_nudge_never_names_a_tool_that_does_not_exist_in_every_context(docs_repo):
    # codicil_status is MCP-only; this text is also printed verbatim by the
    # `codicil query` CLI subcommand, which has no such command.
    (docs_repo / "a.md").write_text("# A\n\nSome content long enough to survive chunking.\n")
    result = server.query_docs("anything")
    assert "codicil_status" not in result["results"]


def test_nudge_absent_on_healthy_semantic_response(docs_repo, fake_embed):
    (docs_repo / "a.md").write_text("# Widgets\n\nContent about widgets and gadgets.\n")
    server.index_repo()

    result = server.query_docs("widgets")
    assert result["backend"] == "semantic"
    assert "unavailable" not in result["results"]
    assert "index exists yet" not in result["results"]
