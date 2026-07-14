# Proposed Postgres Schema v2 (revised after review, 2026-07-14)

Single database `finquery`.

File plan:
- `db/schema.sql`: DDL only, fully idempotent (IF NOT EXISTS).
- `db/seed_master.sql`: DML for master data: lookup tables (values from
  fake-data/category-list.md), the 3 users, static per-user budgets.
- `ingest/seed_transactions.py`: reads fake-data/*.csv, resolves enum names to
  FKs, loads transactions, builds pii_mappings from narrations.
No Alembic (recorded decision): shape changes = drop + re-seed synthetic data.

## Lookup tables (normalized taxonomy)

### 1. categories
| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| name | text unique | Essentials / Lifestyle / Goals |

### 2. subcategories
| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| category_id | int FK categories | |
| name | text | Bills, Groceries, ... (33 rows) |
Unique: (category_id, name).

### 3. spend_types
| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| subcategory_id | int FK subcategories | |
| name | text | Rent, Electricity, ... (133 rows) |
Unique: (subcategory_id, name).

## Core tables

### 4. users
| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| username | text unique | user1 / user2 / user3 |
| persona | text | familyMan / gigFreelancer / youngRenter |
| created_at | timestamptz default now() | |

### 5. transactions
Raw fake PII stays here; it never reaches the LLM unpseudonymized.
| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| user_id | int FK users | |
| txn_date | date | aggregation windows |
| bank_description | text | raw narration WITH fake PII |
| amount | numeric(12,2) | money is never float |
| txn_type | text check in (credit, debit) | |
| category_id | int null FK categories | null for credits |
| subcategory_id | int null FK subcategories | |
| spend_type_id | int null FK spend_types | null where taxonomy defines none |

Indexes: (user_id, txn_date), (user_id, category_id), (user_id, subcategory_id).
Queries can hit any taxonomy level via joins; tools accept level + name and
resolve through the lookup tables.

### 6. budgets
Allocations exist at main-category level AND subcategory level; spend types
carry no allocation (review decision 2026-07-14). A row with subcategory_id
NULL is the category-level allocation; the category total may exceed the sum
of its subcategory rows (headroom for unbudgeted subcategories). Static,
seeded in seed_master.sql, tuned so user1 has a guaranteed over-budget
subcategory. Spend-type-level questions report spending with "no budget
defined at that level."
| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| user_id | int FK users | |
| category_id | int FK categories | always set |
| subcategory_id | int null FK subcategories | NULL = category-level allocation |
| monthly_budget | numeric(12,2) | |
Unique: (user_id, category_id, subcategory_id) NULLS NOT DISTINCT.

### 7. pii_mappings
Forward map real -> fake, consistent per user; doubles as the leakage
scanner's denylist.
| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| user_id | int FK users | isolation boundary |
| pii_type | text check in (vpa, phone, account, card, loan_ref, name) | |
| real_value | text | e.g. 9701234567@ybl |
| fake_value | text | stable pseudonym |
| created_at | timestamptz | |
Unique: (user_id, real_value).

## Knowledge base tables

### 8. kb_documents
One row per source document (original article or extracted booklet). Holds
per-document metadata once: title, publisher, source_url, license. Citations
join through this ("RBI FAME 2024, page 12"); re-chunking never duplicates it.
| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| title | text | |
| doc_type | text check in (article, extracted) | |
| publisher | text | FinQuery / RBI / NCFE |
| source_url | text | |
| license_note | text | |

### 9. kb_chunks
The retrieval units, and THE table that stores vector embeddings for the KB.
Dense + sparse live in the same row, making hybrid+RRF one SQL query.
| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| document_id | int FK kb_documents | |
| chunk_index | int | order within document |
| content | text | ~400 tokens, 15% overlap |
| token_count | int | |
| page_ref | text null | booklet page for provenance |
| embedding | vector(1536) | text-embedding-3-small; exact/flat, no ANN index |
| tsv | tsvector generated from content | sparse side, GIN index |

### 10. rag_transaction_chunks (approach A only)
Vanilla RAG embeds pseudonymized serialized transactions here (the second and
only other table with an embedding column). Separate from kb_chunks so the
agent's KB retrieval is never polluted; agent never touches this table.
| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| user_id | int FK users | |
| content | text | pseudonymized serialized txn(s) |
| source_txn_ids | int[] | provenance |
| embedding | vector(1536) | |
| tsv | tsvector generated | |

## Observability tables

### 11. ask_runs
One row per /ask call. Serves three jobs: (a) tool-sequence record for the
eval metrics (tool-selection accuracy, tool-sequence correctness),
(b) response provenance audit, (c) per-user query history for the UI.
Forward-compatible with CMM-side memory work (a future thread_id is one
ALTER), but multi-turn memory itself stays out of capstone scope per the
frozen design doc (map-reduce memory is in the doc's rejected list).
| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| created_at | timestamptz | |
| user_id | int FK users | |
| approach | text check in (agent, rag) | |
| question | text | |
| answer | text | |
| refused | boolean | |
| tool_calls | jsonb | ordered [{tool, args, ms}]; empty for rag |
| citations | jsonb | as returned to the client |
| latency_ms | int | |

### 12. llm_payload_log
Every LLM-bound payload, for the deterministic 0%-leakage scan (stays in
Postgres per review decision).
| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| created_at | timestamptz | |
| user_id | int | |
| approach | text | agent / rag / judge |
| direction | text check in (to_llm, from_llm) | scan targets to_llm |
| kind | text | system / user / tool_result / retrieval_context |
| content | text | exact payload |

## Resolved in review (2026-07-14)
- Taxonomy normalized into 3 lookup tables with FKs from transactions.
- Budgets: static DML in seed_master.sql; queries supported at all 3 levels
  (subcategory native, category roll-up, spend-type spending-only).
- Transactions populated from CSVs by ingest/seed_transactions.py.
- llm_payload_log stays in Postgres.
- Tool sequence stored per response (ask_runs.tool_calls).
- Chat threads / map-reduce memory: kept OUT of capstone (frozen-spec
  rejection, timeline risk); ask_runs is forward-compatible for CMM later.
