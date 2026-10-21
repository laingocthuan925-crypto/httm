from app.services.semantic_scholar import merge_dedupe
from app.services.pdf_chunker import chunk_pages


def test_merge_dedupe_fills_missing():
    a = [{"title": "X", "doi": "10.1/x", "abstract": None, "oa_url": None}]
    b = [{"title": "X", "doi": "10.1/x", "abstract": "abs", "oa_url": "u"}]
    m = merge_dedupe(a, b)
    assert len(m) == 1 and m[0]["abstract"] == "abs" and m[0]["oa_url"] == "u"


def test_chunk_skips_scanned():
    assert chunk_pages([(1, "x")]) == []


def test_chunk_normal():
    para = "This is a sufficiently long paragraph about methods. " * 10
    pages = [(i, "\n\n".join([para] * 3)) for i in range(1, 4)]
    ch = chunk_pages(pages)
    assert ch and all(len(c["text"]) <= 2200 for c in ch)
