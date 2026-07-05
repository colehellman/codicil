"""Indexing invariants — the headline reliability guarantee lives here.

The one that matters most: a reindex whose embedding step FAILS must leave the
previous index intact. The worst case is stale, never empty.
"""

from codicil import server


def test_index_adds_chunks(docs_repo, fake_embed):
    (docs_repo / "a.md").write_text("# A\n\nSome content about widgets and gadgets.\n")
    indexed, skipped = server.index_repo()
    assert indexed == 1
    assert server.collection.count() >= 1


def test_incremental_reindex_skips_unchanged(docs_repo, fake_embed):
    (docs_repo / "a.md").write_text("# A\n\nStable content that will not change.\n")
    assert server.index_repo()[0] == 1
    indexed, skipped = server.index_repo()  # nothing changed
    assert indexed == 0
    assert skipped >= 1


def test_failed_reindex_preserves_old_chunks(docs_repo, fake_embed, monkeypatch):
    """If embedding fails mid-reindex, the file's existing chunks must survive."""
    f = docs_repo / "a.md"
    f.write_text("# A\n\nORIGINAL content about the payment service.\n")
    assert server.index_repo()[0] == 1
    before = server.collection.get(where={"source": "a.md"})["documents"]
    assert before and "ORIGINAL" in before[0]

    # Rewrite the file, then make embedding fail during a forced reindex.
    f.write_text("# A\n\nTOTALLY DIFFERENT content now, describing the shipping service in detail.\n")

    def boom(_texts):
        raise RuntimeError("embedding host is down")

    monkeypatch.setattr(server, "embed_many", boom)
    indexed, skipped = server.index_repo(force=True)

    assert indexed == 0            # nothing successfully reindexed
    assert skipped >= 1
    after = server.collection.get(where={"source": "a.md"})["documents"]
    assert after == before         # OLD chunks preserved — never wiped
    assert "ORIGINAL" in after[0]


def test_deleted_file_is_removed_from_index(docs_repo, fake_embed):
    f = docs_repo / "a.md"
    f.write_text("# A\n\nContent that will later be deleted from the repository entirely.\n")
    assert server.index_repo()[0] == 1
    assert server.collection.count() >= 1

    f.unlink()
    server.index_repo()
    assert server.collection.get(where={"source": "a.md"})["ids"] == []
