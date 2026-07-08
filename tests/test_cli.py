"""`codicil query` CLI wiring: auto-index when empty, join multi-word args, print results.

No --repo is passed here: server.REPO_PATH is fixed at import time from CODICIL_REPO,
so (like every other test in this suite) these rely on docs_repo's monkeypatch of
server.REPO_PATH rather than the CLI's env var, which only affects a not-yet-imported
server module.
"""

import sys

from codicil import cli, server


def test_query_prints_matching_passage(docs_repo, fake_embed, monkeypatch, capsys):
    (docs_repo / "a.md").write_text("# Widgets\n\nContent about widgets and gadgets.\n")
    monkeypatch.setattr(sys, "argv", ["codicil", "query", "widgets"])

    cli.main()

    assert "a.md" in capsys.readouterr().out


def test_query_indexes_automatically_when_collection_empty(docs_repo, fake_embed, monkeypatch):
    (docs_repo / "a.md").write_text("# Widgets\n\nContent about widgets and gadgets.\n")
    assert server.collection.count() == 0

    monkeypatch.setattr(sys, "argv", ["codicil", "query", "widgets"])
    cli.main()

    assert server.collection.count() > 0


def test_query_joins_multiword_args_and_passes_n_results(docs_repo, fake_embed, monkeypatch):
    (docs_repo / "a.md").write_text("# A\n\nExplains atomic swap reindexing safety.\n")
    server.index_repo()

    captured = {}
    real_query_docs = server.query_docs

    def spy(query, n_results=5):
        captured["query"], captured["n_results"] = query, n_results
        return real_query_docs(query, n_results=n_results)

    monkeypatch.setattr(server, "query_docs", spy)
    monkeypatch.setattr(
        sys, "argv",
        ["codicil", "query", "atomic", "swap", "reindexing", "--n-results", "3"],
    )

    cli.main()

    assert captured["query"] == "atomic swap reindexing"
    assert captured["n_results"] == 3
