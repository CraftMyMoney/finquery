-- FinQuery schema (DDL only, fully idempotent; see db/SCHEMA_DESIGN.md v2).
-- Applied automatically on first container boot (initdb mount) and re-applied
-- any time via: python -m ingest.apply_schema

CREATE EXTENSION IF NOT EXISTS vector;

-- ------------------------------------------------------------ taxonomy lookups
CREATE TABLE IF NOT EXISTS categories (
    id   serial PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS subcategories (
    id          serial PRIMARY KEY,
    category_id int  NOT NULL REFERENCES categories(id),
    name        text NOT NULL,
    UNIQUE (category_id, name)
);

CREATE TABLE IF NOT EXISTS spend_types (
    id             serial PRIMARY KEY,
    subcategory_id int  NOT NULL REFERENCES subcategories(id),
    name           text NOT NULL,
    UNIQUE (subcategory_id, name)
);

-- ------------------------------------------------------------ core
CREATE TABLE IF NOT EXISTS users (
    id         serial PRIMARY KEY,
    username   text NOT NULL UNIQUE,
    persona    text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transactions (
    id               serial PRIMARY KEY,
    user_id          int  NOT NULL REFERENCES users(id),
    txn_date         date NOT NULL,
    bank_description text NOT NULL,          -- raw narration WITH fake PII
    amount           numeric(12,2) NOT NULL CHECK (amount > 0),
    txn_type         text NOT NULL CHECK (txn_type IN ('credit', 'debit')),
    category_id      int REFERENCES categories(id),      -- NULL for credits
    subcategory_id   int REFERENCES subcategories(id),
    spend_type_id    int REFERENCES spend_types(id)
);
CREATE INDEX IF NOT EXISTS idx_txn_user_date ON transactions (user_id, txn_date);
CREATE INDEX IF NOT EXISTS idx_txn_user_cat  ON transactions (user_id, category_id);
CREATE INDEX IF NOT EXISTS idx_txn_user_sub  ON transactions (user_id, subcategory_id);

CREATE TABLE IF NOT EXISTS budgets (
    id             serial PRIMARY KEY,
    user_id        int NOT NULL REFERENCES users(id),
    category_id    int NOT NULL REFERENCES categories(id),
    subcategory_id int REFERENCES subcategories(id),     -- NULL = category-level
    monthly_budget numeric(12,2) NOT NULL,
    UNIQUE NULLS NOT DISTINCT (user_id, category_id, subcategory_id)
);

CREATE TABLE IF NOT EXISTS pii_mappings (
    id         serial PRIMARY KEY,
    user_id    int  NOT NULL REFERENCES users(id),
    pii_type   text NOT NULL CHECK (pii_type IN ('vpa','phone','account','card','loan_ref','policy','name')),
    real_value text NOT NULL,
    fake_value text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, real_value)
);

-- ------------------------------------------------------------ knowledge base
CREATE TABLE IF NOT EXISTS kb_documents (
    id           serial PRIMARY KEY,
    title        text NOT NULL,
    doc_type     text NOT NULL CHECK (doc_type IN ('article', 'extracted')),
    publisher    text NOT NULL,
    source_url   text NOT NULL DEFAULT '',
    license_note text NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS kb_chunks (
    id          serial PRIMARY KEY,
    document_id int  NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    chunk_index int  NOT NULL,
    content     text NOT NULL,
    token_count int  NOT NULL,
    page_ref    text,
    embedding   vector(1536),                -- dense: exact/flat scan, no ANN index
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    UNIQUE (document_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_tsv ON kb_chunks USING gin (tsv);

CREATE TABLE IF NOT EXISTS rag_transaction_chunks (
    id              serial PRIMARY KEY,
    user_id         int  NOT NULL REFERENCES users(id),
    content         text NOT NULL,           -- pseudonymized BEFORE storage/embedding
    source_txn_ids  int[] NOT NULL,
    embedding       vector(1536),
    tsv             tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);
CREATE INDEX IF NOT EXISTS idx_rag_txn_chunks_user ON rag_transaction_chunks (user_id);

-- ------------------------------------------------------------ observability
CREATE TABLE IF NOT EXISTS ask_runs (
    id         serial PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    user_id    int  NOT NULL REFERENCES users(id),
    approach   text NOT NULL CHECK (approach IN ('agent', 'rag')),
    question   text NOT NULL,
    answer     text NOT NULL,
    refused    boolean NOT NULL DEFAULT false,
    tool_calls jsonb NOT NULL DEFAULT '[]',  -- ordered [{tool, args, ms}]
    citations  jsonb NOT NULL DEFAULT '[]',
    latency_ms int
);
CREATE INDEX IF NOT EXISTS idx_ask_runs_user ON ask_runs (user_id, created_at);

CREATE TABLE IF NOT EXISTS llm_payload_log (
    id         serial PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    user_id    int,
    approach   text NOT NULL,                -- agent / rag / judge
    direction  text NOT NULL CHECK (direction IN ('to_llm', 'from_llm')),
    kind       text NOT NULL,                -- system / user / tool_result / retrieval_context
    content    text NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_payload_dir ON llm_payload_log (direction, created_at);
