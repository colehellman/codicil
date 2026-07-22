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


def test_grep_snippet_has_no_duplicate_lines(docs_repo):
    # Keyword on adjacent lines used to produce overlapping, duplicated snippet lines.
    (docs_repo / "b.md").write_text(
        "# Budget\n\nbudget item alpha\nbudget item bravo\nbudget item charlie\n"
    )
    out = server.grep_fallback("budget")
    assert out.count("budget item bravo") == 1


def test_grep_ignores_non_doc_files(docs_repo):
    (docs_repo / "notes.md").write_text("# Notes\n\nbudget planning details.\n")
    (docs_repo / "image.png").write_bytes(b"budget planning binary junk")
    out = server.grep_fallback("budget planning")
    assert "notes.md" in out
    assert "image.png" not in out


def test_extract_keywords_drops_filler_words():
    # A natural-language question (the phrasing an AI assistant actually relays)
    # used to let filler words occupy the 5-keyword cap ahead of the terms that
    # actually distinguish one doc from another. Verified before this fix: the
    # old `[w.lower() for w in query.split() if len(w) > 2][:5]` logic turned this
    # exact query into ['how', 'you', 'handle', 'the', 'retry'] — "request" and
    # "fails" never made it into the window at all.
    kws = server._extract_keywords(
        "How do you handle the retry logic when a request fails and times out"
    )
    assert kws == ["handle", "retry", "logic", "request", "fails"]


def test_extract_keywords_falls_back_when_query_is_all_filler():
    # An all-filler query (every word is a stopword) would otherwise filter down to
    # an empty list, and grep_fallback's `if not keywords` guard would then skip the
    # search entirely — worse than before stopword filtering existed. Falling back
    # to the unfiltered candidates keeps this a no-worse-than-before degradation.
    kws = server._extract_keywords("How do you use this for that")
    assert kws == ["how", "you", "use", "this", "for"]


def test_grep_fallback_still_searches_on_all_filler_query(docs_repo):
    (docs_repo / "a.md").write_text("# A\n\nhow you use this for that reasons.\n")
    out = server.grep_fallback("How do you use this for that")
    assert "No search terms provided" not in out
    assert "a.md" in out
