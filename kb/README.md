# FinQuery Knowledge Base

Corpus for the `search_finance_kb` tool (education Q&A surface). Target: ~500 chunks
(~400 tokens each, 15% overlap) in pgvector with hybrid dense + sparse retrieval.

## Structure

```
kb/
  sources/     # original public PDFs, kept for provenance (never edited)
  extracted/   # booklet content converted to .md with source frontmatter
  articles/    # short original articles written for this project
```

## Sources

| File | Publisher | Pages | Reuse status | URL |
|---|---|---|---|---|
| `rbi_fame_booklet_2024.pdf` | RBI, FAME 4th ed. Feb 2024 | 60 | Reproduction permitted with source acknowledgment (stated in booklet) | rbi.org.in/FinancialEducation/fame.aspx (mirror: slbctn.com) |
| `ncfe_financial_education_part_a.pdf` | NCFE (promoted by RBI/SEBI/IRDAI/PFRDA) | 26 | Public financial-education material; extracts cleanly | ncfe.org.in |
| `ncfe_workshop_reading_material.pdf` | NCFE | 44 | Public; PDF uses custom font encoding, text extraction garbled. Dropped (no OCR tooling on build machine; corpus target met without it). | ncfe.org.in |
| `sebi_financial_education_booklet.pdf` | SEBI | 73 | Carries a no-reproduction notice. REFERENCE ONLY: use facts/benchmarks when writing original articles, do NOT copy text into extracted/. | investor.sebi.gov.in |
| `rbi_beaware_frauds_2022.pdf` | RBI, Office of RBI Ombudsman | 39 | Public-awareness booklet on fraud modus operandi; distributed for public education | rbidocs.rbi.org.in (fetched via cdnbbsr.s3waas.gov.in mirror) |
| `ncfe_handbook_new_entrants.pdf` | NCFE | 60 | Public education material; audience = salaried new joiners, closest match to our personas | ncfe.org.in |
| `ncfe_personal_finance_students.pdf` | NCFE / NCERT | 93 | Public education material; basics + distractor bulk for retrieval ablation | ncfe.org.in |

Corpus status (2026-07-15): ~84k words across extracted/ + articles/, chunked to
354 chunks (avg 322 tokens, max 479) by `retrieval/chunking.py`, loaded by
`python -m ingest.ingest_kb` with embeddings NULL, against the design doc's ~500 estimate.
Delta recorded for Failure Analysis: NCFE "Part B" does not exist (404), and the NCFE
workshop PDF was dropped (garbled encoding, no OCR tooling). ~330 chunks provides
adequate distractor mass for the dense-vs-hybrid ablation.

Copyright stance (recorded for Failure Analysis / Decision Reasoning):
- No copyrighted books are ingested (e.g., trade personal-finance books).
- `extracted/` may contain only material whose publisher permits reproduction
  (RBI FAME with acknowledgment; NCFE education material). Every extracted file
  carries `source` + `source_url` frontmatter.
- SEBI booklet informs original articles (facts are not copyrightable; expression is).

## Extraction plan

1. RBI FAME 2024 -> `extracted/rbi_fame_*.md`, one file per message/topic block,
   frontmatter: `title, source, source_url, publisher, topics`.
2. NCFE Part A -> `extracted/ncfe_part_a_*.md`, one file per chapter section.
3. NCFE workshop material: attempt OCR only if chunk count falls short; else drop.

## Original articles plan (`articles/`)

Written for this project, in our own words, citing public sources. Sized so every
education-bucket golden question has a guaranteed gold chunk. One file per topic,
~600-900 words, H2 sections as chunk boundaries.

| # | Article | Feeds golden questions on | Primary refs |
|---|---|---|---|
| 1 | The 50/30/20 rule and needs vs wants | budgeting basics | SEBI ch.3, industry articles |
| 2 | Emergency fund sizing (3/6/12 months by income stability) | emergency fund | SEBI ch.3, NCFE |
| 3 | Budgeting on irregular income (freelancers/gig) | composite w/ user2-style income | original |
| 4 | EMIs and the debt-to-income ratio (30% ideal, 40% max) | EMI/debt composites | SEBI ch.8, lender guidelines |
| 5 | Term life insurance: what it is, sizing cover (8-10x income + debts) | insurance education | SEBI ch.6 |
| 6 | Why not to mix insurance and investment (ULIP/endowment cost drag) | insurance education | SEBI ch.6 |
| 7 | Health insurance basics and sizing by city | insurance education | SEBI ch.6 |
| 8 | SIPs and rupee cost averaging | investing basics | SEBI ch.5 |
| 9 | PPF, NPS and ELSS compared (lock-ins, tax treatment) | 80C instruments | SEBI ch.4/7/9 |
| 10 | Section 80C and old vs new tax regime, the 30-second version | tax education | Income Tax Act public info |
| 11 | Credit scores in India: what moves your CIBIL score | credit education | RBI FAME, bureau documentation |
| 12 | Credit cards and revolving debt: the true cost of minimum due | credit education | RBI FAME |
| 13 | Inflation and compounding: why starting early matters | core concepts | SEBI ch.2, RBI FAME |
| 14 | Asset allocation and the 100-minus-age heuristic | investing basics | industry articles |
| 15 | Nomination vs will: what a nominee actually is | estate basics | SEBI ch.7 |
| 16 | UPI and digital payment safety | fraud awareness | RBI FAME |
| 17 | Retirement corpus rules of thumb (income multiples by age) | retirement education | industry articles |

Boundary note: articles teach principles and general benchmarks only. No product
recommendations, no named funds/policies as advice. This keeps every article on the
allowed side of the refusal boundary (specificity filter): applying a principle to the
user's numbers is education; "should I buy X" is refused.
