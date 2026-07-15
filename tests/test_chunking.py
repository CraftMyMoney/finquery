"""Unit tests for the KB chunker. Pure local: no DB, no API key.

Covers the real corpus (every kb/ file chunks within budget, page refs and
H2 headings preserved) plus synthetic cases for the overlap and boundary
rules that real files cannot pin down deterministically.
"""

import re
from pathlib import Path

from retrieval.chunking import (
    MAX_TOKENS,
    MIN_BREAK_TOKENS,
    OVERLAP_TOKENS,
    chunk_file,
    chunk_kb,
    count_tokens,
    parse_frontmatter,
)

KB = Path(__file__).resolve().parent.parent / "kb"


# ---------------------------------------------------------------- frontmatter

def test_frontmatter_parsing_article_and_extracted():
    meta, body = parse_frontmatter(
        (KB / "articles" / "01-fifty-thirty-twenty-rule.md").read_text()
    )
    assert meta["title"] == "The 50/30/20 Rule and Needs vs Wants"
    assert meta["source"] == "FinQuery original article"
    assert "refs" not in meta or meta["refs"] == ""  # list values are skipped
    assert body.lstrip().startswith("# ")

    meta, _ = parse_frontmatter((KB / "extracted" / "rbi_fame_2024.md").read_text())
    assert meta["publisher"].startswith("Reserve Bank of India")
    assert meta["source_url"].startswith("https://")


# ---------------------------------------------------------------- real corpus

def test_article_chunks_keep_h2_headings_and_have_no_page_refs():
    doc = chunk_file(KB / "articles" / "01-fifty-thirty-twenty-rule.md")
    assert doc.doc_type == "article"
    assert doc.publisher == "FinQuery original article"
    assert doc.chunks[0].content.startswith("## ")
    assert all(c.page_ref is None for c in doc.chunks)


def test_extracted_chunks_carry_page_refs():
    doc = chunk_file(KB / "extracted" / "rbi_fame_2024.md")
    assert doc.doc_type == "extracted"
    assert all(
        c.page_ref and re.fullmatch(r"Page \d+|Pages \d+-\d+", c.page_ref)
        for c in doc.chunks
    )


def test_whole_corpus_within_budget():
    docs = chunk_kb(KB)
    assert len(docs) == 22  # 17 articles + 5 extracted booklets
    total = 0
    for doc in docs:
        assert doc.chunks, f"{doc.path} produced no chunks"
        assert [c.chunk_index for c in doc.chunks] == list(range(len(doc.chunks)))
        for c in doc.chunks:
            # joining paragraphs adds a few separator tokens over the packed sum
            assert 0 < c.token_count <= MAX_TOKENS + 16, (doc.path, c.chunk_index)
        total += len(doc.chunks)
    # kb/README estimate is ~330; fail loudly if the corpus or chunker drifts
    assert 200 <= total <= 550, total


# ---------------------------------------------------------------- synthetic

def _write(tmp_path: Path, name: str, text: str) -> Path:
    d = tmp_path / "articles"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_text(text)
    return p


def test_intra_section_break_carries_overlap(tmp_path):
    para = "Money kept idle loses value to inflation every single year. " * 4
    body = "## One Long Section\n\n" + "\n\n".join(para.strip() for _ in range(20))
    doc = chunk_file(_write(tmp_path, "long.md", body))
    assert len(doc.chunks) > 1
    for prev, nxt in zip(doc.chunks, doc.chunks[1:]):
        head = nxt.content.split("\n\n")[0]
        assert head in prev.content, "next chunk must start with the previous tail"
        assert count_tokens(head) <= OVERLAP_TOKENS


def test_section_boundary_breaks_clean_without_overlap(tmp_path):
    para = "A sentence about budgets that repeats to build section size. " * 5
    section = "\n\n".join(para.strip() for _ in range(6))  # ~330 tokens > MIN_BREAK
    body = f"## First Topic\n\n{section}\n\n## Second Topic\n\n{section}"
    doc = chunk_file(_write(tmp_path, "two.md", body))
    assert len(doc.chunks) == 2
    assert doc.chunks[1].content.startswith("## Second Topic")
    assert "First Topic" not in doc.chunks[1].content


def test_tiny_sections_pack_together(tmp_path):
    body = "\n\n".join(f"## Tip {i}\n\nSave first, spend later." for i in range(6))
    doc = chunk_file(_write(tmp_path, "tips.md", body))
    assert len(doc.chunks) == 1  # each section is far below MIN_BREAK_TOKENS
    assert doc.chunks[0].token_count < MIN_BREAK_TOKENS


def test_pathological_unpunctuated_page_is_hard_split(tmp_path):
    words = "compounding inflation liquidity diversification nomination " * 250
    body = f"## Page 7\n\n{words.strip()}"
    d = tmp_path / "extracted"
    d.mkdir()
    p = d / "garbled.md"
    p.write_text(body)
    doc = chunk_file(p)
    assert doc.doc_type == "extracted"
    assert len(doc.chunks) > 1
    assert all(c.token_count <= MAX_TOKENS + 16 for c in doc.chunks)
    assert all(c.page_ref == "Page 7" for c in doc.chunks)
