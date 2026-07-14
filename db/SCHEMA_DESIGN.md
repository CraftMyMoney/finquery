# Proposed Postgres Schema (for approval, then becomes db/schema.sql)

Single database `finquery`. All idempotent DDL (IF NOT EXISTS). No Alembic:
shape changes are handled by drop + re-seed of synthetic data (recorded decision).

## 1. users
Who: the 3 personas. Why: per-user PII isolation and per-user tool scoping.

| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| username | text unique | user1 / user2 / user3 |
| persona | text | familyMan / gigFreelancer / youngRenter, for docs and demo |
| created_at | timestamptz default now() | |

## 2. transactions
Why: the SQL surface for the 5 SQL tools. Raw fake PII stays here; it never
reaches the LLM unpseudonymized.

| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| user_id | int FK users | |
| txn_date | date | aggregation windows |
| bank_description | text | raw narration WITH fake PII (the pseudonymizer's input) |
| amount | numeric(12,2) | money is never float |
| txn_type | text check in (credit, debit) | income vs spend |
| category | text null | Essentials / Lifestyle / Goals; null for credits |
| subcategory | text null | from category-list.md |
| spend_type | text null | from category-list.md; null where none defined |

Indexes: (user_id, txn_date), (user_id, category, subcategory).

## 3. budgets
Why: budget_vs_actual tool needs a comparison target. Seeded per user at
subcategory level with at least one over-budget subcategory guaranteed.

| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| user_id | int FK users | |
| subcategory | text | budget granularity = subcategory |
| monthly_budget | numeric(12,2) | fixed monthly allowance |

Unique: (user_id, subcategory).

## 4. pii_mappings
Why: the core of the pseudonymization layer AND the leakage scanner's
denylist. Forward map real -> fake, consistent per user.

| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| user_id | int FK users | isolation boundary |
| pii_type | text check in (vpa, phone, account, card, loan_ref, name) | detector class |
| real_value | text | e.g. 9701234567@ybl |
| fake_value | text | e.g. vendor01@fakebank, stable across calls |
| created_at | timestamptz | |

Unique: (user_id, real_value). The 0%-leakage eval scans every LLM-bound
payload for any real_value in this table.

## 5. kb_documents
Why: provenance root for citations.

| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| title | text | e.g. "Emergency Fund, How Big and Where to Keep It" |
| doc_type | text check in (article, extracted) | original vs booklet |
| publisher | text | FinQuery / RBI / NCFE |
| source_url | text | |
| license_note | text | recorded reuse basis |

## 6. kb_chunks
Why: the retrieval surface (both dense and sparse live here; hybrid+RRF is
one SQL query).

| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| document_id | int FK kb_documents | citation join |
| chunk_index | int | order within document |
| content | text | ~400 tokens, 15% overlap |
| token_count | int | chunking audit |
| page_ref | text null | booklet page for provenance ("Page 12") |
| embedding | vector(1536) | text-embedding-3-small; exact/flat scan, no ANN index |
| tsv | tsvector generated from content | sparse side, GIN indexed |

Also embedded here for approach A: serialized transaction rows as chunks of a
per-user pseudo-document? NO. Decision: approach A gets its own table
`rag_transaction_chunks` (same shape, user_id column added) so KB retrieval
quality in approach B is never polluted by transaction chunks. See table 7.

## 7. rag_transaction_chunks (approach A only)
Why: vanilla RAG embeds serialized (pseudonymized) transactions; the agent
never touches this table. Keeping it separate keeps the comparison clean.

| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| user_id | int FK users | |
| content | text | pseudonymized serialized txn(s) |
| source_txn_ids | int[] | provenance back to transactions |
| embedding | vector(1536) | |
| tsv | tsvector generated | |

## 8. llm_payload_log
Why: the 0%-leakage metric requires scanning EVERY LLM-bound payload. Logging
them makes the scan deterministic, auditable, and re-runnable after the fact.

| Column | Type | Purpose |
|---|---|---|
| id | serial PK | |
| created_at | timestamptz | |
| user_id | int | |
| approach | text | agent / rag / judge |
| direction | text check in (to_llm, from_llm) | leakage scan targets to_llm |
| kind | text | system / user / tool_result / retrieval_context |
| content | text | the exact payload |

## Open questions for you
1. Budget granularity: subcategory-level only, or also a category-level total?
2. llm_payload_log in Postgres vs JSONL files: I prefer Postgres (queryable,
   one datastore), files would also work.
3. Any CMM-side conventions you want mirrored in naming (snake_case tables
   assumed)?
