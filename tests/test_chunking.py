"""Chunking splits documents sensibly and tags each chunk with its source."""

from codicil import server


def test_chunk_markdown_splits_on_headers():
    text = "# Title\n\nintro\n\n## Section A\n\nbody a\n\n## Section B\n\nbody b\n"
    chunks = server.chunk_markdown(text)
    # one chunk per top-level section (title, A, B)
    assert len(chunks) == 3
    assert chunks[1].startswith("## Section A")


def test_chunk_prepends_source_path():
    chunks = server.chunk("# Big Header\n\n" + "word " * 50, "docs/x.md")
    assert chunks
    assert all(c.startswith("[docs/x.md]") for c in chunks)


def test_chunk_drops_tiny_fragments():
    # Below the 40-char floor → nothing worth indexing.
    assert server.chunk("# hi", "docs/x.md") == []


def test_oversized_section_is_subdivided_with_overlap():
    big = "x" * 4000
    chunks = server.chunk_generic(big)
    assert len(chunks) >= 3
    # consecutive chunks overlap by OVERLAP chars
    assert chunks[0][-server.OVERLAP:] == chunks[1][: server.OVERLAP]
