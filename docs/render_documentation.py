"""Render docs/documentation.md to the submitted PDF deliverable.

markdown -> print-styled HTML -> Chrome headless -> PDF, then report the page
count, because the capstone caps documentation at 4-5 pages and guessing from
word count is unreliable once diagrams and tables are in.

Same toolchain as the design doc (see CLAUDE.md): no pandoc or poppler on this
machine, so Chrome does the printing and pypdf does the verification. Image
paths in the markdown are relative to docs/, which is why the HTML is written
there too.

Usage:
    python docs/render_documentation.py
"""

import subprocess
import sys
from pathlib import Path

import markdown
from pypdf import PdfReader

DOCS = Path(__file__).resolve().parent
CHROME = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

# Tight but readable: the 4-5 page cap is a hard constraint, so margins and
# leading are deliberately economical. break-inside: avoid keeps diagrams and
# tables whole, matching the design doc's print rules.
CSS = """
@page { size: A4; margin: 14mm 15mm; }
body { font: 10pt/1.39 -apple-system, "Helvetica Neue", Arial, sans-serif;
       color: #16181d; }
h1 { font-size: 17pt; margin: 0 0 2pt; }
h2 { font-size: 12pt; margin: 13pt 0 5pt; padding-top: 3pt;
     border-top: 1px solid #d6dae1; break-after: avoid; }
h3 { font-size: 10.5pt; margin: 9pt 0 3pt; break-after: avoid; }
p, li { margin: 0 0 4pt; }
ul { margin: 0 0 5pt; padding-left: 16px; }
hr { display: none; }
img { max-width: 66%; display: block; margin: 5pt auto; break-inside: avoid; }
table { border-collapse: collapse; width: 100%; font-size: 9pt;
        margin: 5pt 0 7pt; break-inside: avoid; }
th, td { border: 1px solid #ccd2da; padding: 2.5pt 5pt; text-align: left; }
th { background: #eef1f5; }
code { font-family: "SF Mono", Menlo, monospace; font-size: 8.8pt;
       background: #f0f2f5; padding: 0.5pt 2.5pt; border-radius: 2px; }
pre { background: #f5f7f9; border: 1px solid #e2e6eb; border-radius: 3px;
      padding: 5pt 7pt; font-size: 8.5pt; overflow: hidden;
      break-inside: avoid; }
pre code { background: none; padding: 0; }
a { color: #1a4d8f; text-decoration: none; }
blockquote { margin: 0 0 5pt; padding-left: 9pt; border-left: 2px solid #ccd2da;
             color: #4a5058; }
"""


def main() -> int:
    src = DOCS / "documentation.md"
    html_path = DOCS / "documentation.html"
    pdf_path = DOCS / "documentation.pdf"

    body = markdown.markdown(
        src.read_text(),
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
    )
    html_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>FinQuery: Project Documentation</title>"
        f"<style>{CSS}</style></head><body>{body}</body></html>"
    )

    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={pdf_path}", html_path.as_uri()],
        check=True, capture_output=True,
    )

    pages = len(PdfReader(pdf_path).pages)
    limit = 5
    print(f"{pdf_path.relative_to(DOCS.parent)}: {pages} pages "
          f"(limit {limit})  {'OK' if pages <= limit else 'OVER, trim needed'}")
    return 0 if pages <= limit else 1


if __name__ == "__main__":
    sys.exit(main())
