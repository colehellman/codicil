"""codicil_status checks health on demand, without waiting for a real query
to reveal degradation — unlike query_docs, it always probes the embedding host.
"""

import threading
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
    assert result["canary_ok"] is False
    assert result["canary_score"] is None


def test_status_canary_ok_when_embeddings_are_genuinely_related(docs_repo, monkeypatch):
    def controlled_embed(text, kind="query"):
        if text == server._CANARY_QUERY:
            return [1.0, 0.0]
        if text == server._CANARY_DOCUMENT:
            return [0.9, 0.436]  # cosine ~0.9 — comfortably above MIN_SCORE
        return [0.5, 0.5]

    monkeypatch.setattr(server, "embed", controlled_embed)
    result = server.codicil_status()
    assert result["canary_ok"] is True
    assert result["canary_score"] >= server.MIN_SCORE
    assert result["backend"] == "semantic"
    assert result["degraded_since"] is None


def test_status_canary_fails_when_embed_succeeds_but_is_untrustworthy(docs_repo, monkeypatch):
    # A wrong model or corrupted response can still let embed() return *something*
    # without raising RuntimeError -- this must still count as degraded, since
    # query_docs's real answers would be equally corrupted by the same cause.
    def controlled_embed(text, kind="query"):
        if text == server._CANARY_QUERY:
            return [1.0, 0.0]
        if text == server._CANARY_DOCUMENT:
            return [0.0, 1.0]  # orthogonal -- cosine 0.0, clearly below MIN_SCORE
        return [0.5, 0.5]

    monkeypatch.setattr(server, "embed", controlled_embed)
    result = server.codicil_status()
    assert result["canary_ok"] is False
    assert result["canary_score"] < server.MIN_SCORE
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


def test_query_docs_success_does_not_clear_a_canary_flagged_degradation(docs_repo, monkeypatch):
    # Regression: query_docs's "embed() didn't raise" signal is weaker than
    # codicil_status's canary check -- it never verifies embedding *quality*.
    # A corrupted-but-reachable model can let ordinary queries succeed via
    # query_docs while the canary still (correctly) sees it as untrustworthy.
    # query_docs's success must not wipe that degradation, or degraded_since
    # would keep resetting to "now" every time query_docs happens to succeed,
    # instead of preserving the true onset.
    (docs_repo / "a.md").write_text("# A\n\nSome content long enough to survive chunking.\n")

    # 16-dim vectors: the shared Chroma collection's dimension gets fixed by
    # whichever test writes to it first in this session (via fake_vec, dim=16) --
    # a mismatched dimension here would raise, not just produce a wrong score.
    plausible_vec = [0.6] * 8 + [0.8] * 8

    def working_embed(text, kind="document"):
        return plausible_vec

    monkeypatch.setattr(server, "embed", working_embed)
    monkeypatch.setattr(server, "embed_many", lambda texts: [working_embed(t) for t in texts])
    server.index_repo()

    def flaky_embed(text, kind="query"):
        if text == server._CANARY_QUERY:
            return [1.0] + [0.0] * 15
        if text == server._CANARY_DOCUMENT:
            return [0.0] * 15 + [1.0]  # orthogonal -- canary fails
        return plausible_vec  # ordinary queries still get a plausible-looking vector

    monkeypatch.setattr(server, "embed", flaky_embed)

    onset = server.codicil_status()["degraded_since"]
    assert onset is not None

    result = server.query_docs("anything")
    assert result["backend"] == "semantic"  # query_docs has no way to know better

    assert server.codicil_status()["degraded_since"] == onset  # onset preserved, not reset


def test_query_docs_still_clears_its_own_connectivity_degradation(docs_repo, monkeypatch):
    # A genuine connectivity-only degradation (no canary involved) must still be
    # clearable by query_docs's own recovery -- this is the pre-existing, tested
    # behavior from the PR that introduced degradation tracking; must not regress.
    plausible_vec = [0.6] * 8 + [0.8] * 8
    (docs_repo / "a.md").write_text("# A\n\nSome content long enough to survive chunking.\n")
    monkeypatch.setattr(server, "embed", lambda text, kind="query": plausible_vec)
    monkeypatch.setattr(server, "embed_many", lambda texts: [plausible_vec for _ in texts])
    server.index_repo()  # non-empty collection so query_docs actually reaches embed()

    def broken_embed(text, kind="query"):
        raise RuntimeError("cannot reach embedding host")

    monkeypatch.setattr(server, "embed", broken_embed)
    assert server.query_docs("anything")["degraded_since"] is not None

    monkeypatch.setattr(server, "embed", lambda text, kind="query": plausible_vec)
    result = server.query_docs("anything")
    assert result["backend"] == "semantic"
    assert result["degraded_since"] is None


def test_status_canary_success_clears_a_prior_connectivity_degradation(docs_repo, monkeypatch):
    # codicil_status's canary-validated success is the stronger signal -- it
    # should be able to clear a degradation query_docs set from a connectivity
    # failure, not just one it set itself.
    plausible_vec = [0.6] * 8 + [0.8] * 8
    (docs_repo / "a.md").write_text("# A\n\nSome content long enough to survive chunking.\n")
    monkeypatch.setattr(server, "embed", lambda text, kind="query": plausible_vec)
    monkeypatch.setattr(server, "embed_many", lambda texts: [plausible_vec for _ in texts])
    server.index_repo()

    def broken_embed(text, kind="query"):
        raise RuntimeError("cannot reach embedding host")

    monkeypatch.setattr(server, "embed", broken_embed)
    assert server.query_docs("anything")["degraded_since"] is not None

    def working_embed(text, kind="query"):
        if text == server._CANARY_QUERY:
            return [1.0] + [0.0] * 15
        if text == server._CANARY_DOCUMENT:
            return [0.9] + [0.436] + [0.0] * 14  # ~0.9 cosine with the query vector above
        return plausible_vec

    monkeypatch.setattr(server, "embed", working_embed)
    result = server.codicil_status()
    assert result["canary_ok"] is True
    assert result["degraded_since"] is None


def test_status_does_not_block_concurrent_query_docs_during_slow_embed(docs_repo, monkeypatch):
    # Regression: codicil_status used to hold _index_lock for its entire body,
    # including the live embed() probe -- a slow/unresponsive embed host meant a
    # concurrent query_docs call (even one needing no embed at all, on an empty
    # collection) was blocked for the same duration. The embed() probe must run
    # outside the lock; only the bookkeeping after it needs to be serialized.
    def slow_embed(text, kind="query"):
        time.sleep(0.3)
        raise RuntimeError("simulated slow, unresponsive embed host")

    monkeypatch.setattr(server, "embed", slow_embed)

    durations = {}

    def call_status():
        t0 = time.time()
        server.codicil_status()
        durations["status"] = time.time() - t0

    def call_query_docs():
        time.sleep(0.05)  # let codicil_status start (and begin its slow embed call) first
        t0 = time.time()
        server.query_docs("anything")  # empty collection -> no embed call needed
        durations["query_docs"] = time.time() - t0

    t1 = threading.Thread(target=call_status)
    t2 = threading.Thread(target=call_query_docs)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert durations["status"] >= 0.3  # actually waited out the slow embed call
    assert durations["query_docs"] < 0.1  # must not be blocked behind it
