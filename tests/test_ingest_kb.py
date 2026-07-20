"""KB ingest test against the live DB: load() must be idempotent and leave
embeddings NULL (backfilled post-key) with the tsv sparse index populated.
Skips cleanly if the dockerized Postgres is not reachable.

load() is destructive by design (DELETE FROM kb_documents cascades to
kb_chunks), so it runs inside a rolled-back transaction. Without that, every
test run silently discards the embedding backfill and leaves vanilla RAG
dead until someone re-runs ingest.embed_chunks."""

import asyncpg
import pytest

from app.config import settings
from ingest.ingest_kb import load


async def test_ingest_kb_is_idempotent_and_leaves_embeddings_null():
    try:
        conn = await asyncpg.connect(settings.database_url)
    except Exception:
        pytest.skip("seeded DB not reachable on DATABASE_URL")
    tr = conn.transaction()
    await tr.start()
    try:
        counts = await load(conn)
        counts_again = await load(conn)  # wipe-and-reload must be repeatable
        assert counts == counts_again

        total = await conn.fetchval("SELECT count(*) FROM kb_chunks")
        assert total == sum(counts.values())
        assert await conn.fetchval("SELECT count(*) FROM kb_documents") == len(counts)
        assert await conn.fetchval(
            "SELECT count(*) FROM kb_chunks WHERE embedding IS NOT NULL"
        ) == 0
        assert await conn.fetchval(
            "SELECT count(*) FROM kb_chunks WHERE tsv IS NULL"
        ) == 0

        # sparse index is queryable right now, before any embedding exists
        hit = await conn.fetchrow(
            """
            SELECT c.content, d.title
            FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id
            WHERE c.tsv @@ plainto_tsquery('english', 'emergency fund months')
            ORDER BY ts_rank_cd(c.tsv, plainto_tsquery('english', 'emergency fund months')) DESC
            LIMIT 1
            """
        )
        assert hit is not None and "emergency" in hit["content"].lower()
    finally:
        await tr.rollback()   # restores the pre-test rows, embeddings included
        await conn.close()
