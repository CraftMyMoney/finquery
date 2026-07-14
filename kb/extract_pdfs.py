"""Extract reproduction-permitted KB source PDFs to markdown.

Only sources whose publisher permits reproduction are extracted (see kb/README.md):
  - RBI FAME booklet 2024 (reproduction permitted with acknowledgment)
  - NCFE Financial Education Part A (public education material)
The SEBI booklet is reference-only and is deliberately NOT extracted.
The NCFE workshop PDF is skipped (garbled font encoding; OCR fallback only if
the corpus falls short of the chunk target).

Output: kb/extracted/<name>.md with source frontmatter and per-page markers
(page numbers feed citation/provenance metadata at chunking time).

Usage: python3 kb/extract_pdfs.py
"""

import re
from pathlib import Path

from pypdf import PdfReader

KB = Path(__file__).parent

SOURCES = [
    {
        "pdf": "rbi_fame_booklet_2024.pdf",
        "out": "rbi_fame_2024.md",
        "title": "Financial Awareness Messages (FAME), Fourth Edition",
        "publisher": "Reserve Bank of India, Financial Inclusion & Development Department",
        "source_url": "https://www.rbi.org.in/FinancialEducation/fame.aspx",
        "license_note": "Reproduction permitted provided the source is acknowledged (stated in booklet).",
    },
    {
        "pdf": "ncfe_financial_education_part_a.pdf",
        "out": "ncfe_part_a.md",
        "title": "Financial Education Part A",
        "publisher": "National Centre for Financial Education (NCFE)",
        "source_url": "https://ncfe.org.in/",
        "license_note": "Public financial-education material by NCFE (promoted by RBI, SEBI, IRDAI, PFRDA).",
    },
]


def clean(text):
    """Normalize extracted text: collapse whitespace, drop empty artifacts."""
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        # drop bare page numbers and decorative runs
        if not line or re.fullmatch(r"[\d\s.|_-]+", line):
            continue
        lines.append(line)
    return "\n".join(lines)


def extract(src):
    reader = PdfReader(KB / "sources" / src["pdf"])
    parts = [
        "---",
        f"title: {src['title']}",
        f"publisher: {src['publisher']}",
        f"source_pdf: kb/sources/{src['pdf']}",
        f"source_url: {src['source_url']}",
        f"license_note: {src['license_note']}",
        "---",
        "",
        f"# {src['title']}",
        "",
        f"Source: {src['publisher']}. {src['license_note']}",
    ]
    kept = 0
    for i, page in enumerate(reader.pages, start=1):
        text = clean(page.extract_text() or "")
        if len(text) < 80:  # covers, blank and image-only pages
            continue
        parts += ["", f"## Page {i}", "", text]
        kept += 1
    out = KB / "extracted" / src["out"]
    out.write_text("\n".join(parts) + "\n")
    print(f"{src['pdf']}: kept {kept}/{len(reader.pages)} pages -> extracted/{src['out']}")


if __name__ == "__main__":
    for src in SOURCES:
        extract(src)
