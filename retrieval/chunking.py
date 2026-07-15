"""Chunking for KB markdown: ~400-token chunks, 15% overlap, H2 sections as
preferred boundaries. Frontmatter (title/refs/topics or publisher/page markers)
becomes chunk metadata for citations. Key-independent; embedding is not.

How it works: paragraphs (blank-line separated) are the atoms. Chunks pack
whole paragraphs up to MAX_TOKENS; an H2 boundary closes the current chunk
early once it holds MIN_BREAK_TOKENS, so sections start fresh chunks where
possible while tiny sections (e.g. sparse booklet pages) still pack together.
The 15% overlap (OVERLAP_TOKENS) is applied only when a break falls inside a
section; H2/page boundaries are semantic and get clean breaks. Extracted
booklets use their '## Page N' markers for the chunk's page_ref citation;
article chunks keep the H2 heading inline as retrieval context.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import tiktoken
from pydantic import BaseModel

TARGET_TOKENS = 400      # design doc: ~400-token chunks
MAX_TOKENS = 480         # hard cap per chunk (target + 20% slack)
OVERLAP_TOKENS = 60      # 15% of target, carried across intra-section breaks
MIN_BREAK_TOKENS = 240   # a section boundary closes a chunk only past this

_H2 = re.compile(r"^## (.+)$", re.MULTILINE)
_PAGE = re.compile(r"Page (\d+)")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class Chunk(BaseModel):
    chunk_index: int
    content: str
    token_count: int
    page_ref: str | None = None


class ChunkedDocument(BaseModel):
    path: str
    title: str
    doc_type: Literal["article", "extracted"]
    publisher: str
    source_url: str = ""
    license_note: str = ""
    chunks: list[Chunk]


@dataclass
class _Atom:
    text: str
    tokens: int
    page: int | None
    section_start: bool


@lru_cache(maxsize=1)
def _encoder() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")  # text-embedding-3-* tokenizer


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text))


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Minimal frontmatter reader for the scalar keys the DB needs
    (title, publisher, source_url, license_note, source). Nested list items
    (refs/topics) are skipped; they are not stored."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.index("\n---\n", 4)
    meta: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line[0] in " \t-":
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, text[end + 5:]


def _split_sections(body: str) -> list[tuple[str | None, str]]:
    """Split on H2 headings. The preamble before the first H2 (H1 title and
    source line, duplicated by frontmatter) is dropped. A body without H2s
    becomes a single heading-less section."""
    parts = _H2.split(body)
    if len(parts) == 1:
        return [(None, body)]
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts), 2)]


def _split_long(text: str, max_tokens: int) -> list[str]:
    """Split an oversized paragraph on sentence ends, keeping ~OVERLAP_TOKENS
    of trailing sentences between pieces. Falls back to a hard token split for
    pathological run-ons (e.g. booklet pages extracted without punctuation)."""
    if count_tokens(text) <= max_tokens:
        return [text]
    pieces: list[str] = []
    cur: list[str] = []
    cur_t = 0
    for sentence in _SENTENCE_END.split(text):
        st = count_tokens(sentence)
        if st > max_tokens:
            if cur:
                pieces.append(" ".join(cur))
                cur, cur_t = [], 0
            ids = _encoder().encode(sentence)
            step = max_tokens - OVERLAP_TOKENS
            for i in range(0, len(ids), step):
                pieces.append(_encoder().decode(ids[i:i + max_tokens]))
            continue
        if cur and cur_t + st > max_tokens:
            pieces.append(" ".join(cur))
            keep: list[str] = []
            kept = 0
            for prev in reversed(cur):
                pt = count_tokens(prev)
                if kept + pt > OVERLAP_TOKENS:
                    break
                keep.insert(0, prev)
                kept += pt
            cur, cur_t = keep, kept
        cur.append(sentence)
        cur_t += st
    if cur:
        pieces.append(" ".join(cur))
    return pieces


def _pack(atoms: list[_Atom]) -> list[Chunk]:
    chunks: list[Chunk] = []
    cur: list[_Atom] = []
    cur_tokens = 0

    def close() -> None:
        content = "\n\n".join(a.text for a in cur)
        pages = [a.page for a in cur if a.page is not None]
        page_ref = None
        if pages:
            lo, hi = min(pages), max(pages)
            page_ref = f"Page {lo}" if lo == hi else f"Pages {lo}-{hi}"
        chunks.append(Chunk(chunk_index=len(chunks), content=content,
                            token_count=count_tokens(content), page_ref=page_ref))

    for atom in atoms:
        if cur and (cur_tokens + atom.tokens > MAX_TOKENS
                    or (atom.section_start and cur_tokens >= MIN_BREAK_TOKENS)):
            close()
            if atom.section_start:
                cur, cur_tokens = [], 0
            else:
                carry: list[_Atom] = []
                carried = 0
                for a in reversed(cur):
                    if carried + a.tokens > OVERLAP_TOKENS:
                        break
                    carry.insert(0, a)
                    carried += a.tokens
                cur, cur_tokens = carry, carried
        cur.append(atom)
        cur_tokens += atom.tokens
    if cur:
        close()
    return chunks


def chunk_file(path: Path) -> ChunkedDocument:
    meta, body = parse_frontmatter(path.read_text())
    doc_type: Literal["article", "extracted"] = (
        "article" if path.parent.name == "articles" else "extracted"
    )
    atoms: list[_Atom] = []
    for heading, text in _split_sections(body):
        page_match = _PAGE.fullmatch(heading) if heading else None
        page = int(page_match.group(1)) if page_match else None
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
            continue
        if heading and page is None:
            paragraphs[0] = f"## {heading}\n\n{paragraphs[0]}"
        first = True
        for para in paragraphs:
            for piece in _split_long(para, TARGET_TOKENS):
                atoms.append(_Atom(piece, count_tokens(piece), page, first))
                first = False
    return ChunkedDocument(
        path=str(path),
        title=meta.get("title", path.stem),
        doc_type=doc_type,
        publisher=meta.get("publisher") or meta.get("source") or "FinQuery",
        source_url=meta.get("source_url", ""),
        license_note=meta.get("license_note", ""),
        chunks=_pack(atoms),
    )


def chunk_kb(kb_dir: Path) -> list[ChunkedDocument]:
    """Chunk the whole corpus: original articles first, then extracted booklets."""
    files = sorted((kb_dir / "articles").glob("*.md")) + sorted(
        (kb_dir / "extracted").glob("*.md")
    )
    return [chunk_file(p) for p in files]
