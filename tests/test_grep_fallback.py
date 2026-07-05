"""Keyword fallback finds the right file with no embeddings and no index."""

from codicil import server


def test_grep_finds_relevant_file(docs_repo):
    (docs_repo / "auth.md").write_text("# Authentication\n\nOAuth2 proxy and SSO login.\n")
    (docs_repo / "deploy.md").write_text("# Deployment\n\nKubernetes blue/green rollout.\n")

    out = server.grep_fallback("authentication login")
    assert "auth.md" in out
    # deploy.md shares no query keywords → should not surface
    assert "deploy.md" not in out


def test_grep_reports_no_matches(docs_repo):
    (docs_repo / "a.md").write_text("# A\n\nnothing relevant here.\n")
    out = server.grep_fallback("zzzzz nonexistent xterm")
    assert "no matches" in out.lower()


def test_grep_ignores_non_doc_files(docs_repo):
    (docs_repo / "notes.md").write_text("# Notes\n\nbudget planning details.\n")
    (docs_repo / "image.png").write_bytes(b"budget planning binary junk")
    out = server.grep_fallback("budget planning")
    assert "notes.md" in out
    assert "image.png" not in out
