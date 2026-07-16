"""Backfill NULL embeddings in kb_chunks and rag_transaction_chunks with
text-embedding-3-small (1536 dims, matches the vector(1536) columns).

Idempotent: only rows WHERE embedding IS NULL are touched, so re-running
after a partial failure or after re-ingesting picks up where it left off.
Re-ingest scripts wipe their tables, which resets embedding to NULL, so the
sequence "ingest -> embed" always converges.

Usage:
    python -m ingest.embed_chunks
"""

import asyncio

import asyncpg
from openai import AsyncOpenAI

from app.config import settings
from retrieval.hybrid import vector_literal

BATCH_SIZE = 100  # chunks are <=480 tokens, so a batch stays far below API limits
TABLES = ("kb_chunks", "rag_transaction_chunks")


async def embed_table(conn: asyncpg.Connection, client: AsyncOpenAI,
                      table: str) -> tuple[int, int]:
    """Embed every NULL-embedding row. Returns (rows embedded, tokens used)."""
    rows = await conn.fetch(
        f"SELECT id, content FROM {table} WHERE embedding IS NULL ORDER BY id"
    )
    tokens = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=[r["content"] for r in batch],
        )
        tokens += response.usage.total_tokens
        await conn.executemany(
            f"UPDATE {table} SET embedding = $1::vector WHERE id = $2",
            [(vector_literal(item.embedding), row["id"])
             for item, row in zip(response.data, batch)],
        )
    return len(rows), tokens


async def main() -> None:
    if not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is empty in .env; nothing embedded")
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    conn = await asyncpg.connect(settings.database_url)
    try:
        grand_tokens = 0
        for table in TABLES:
            embedded, tokens = await embed_table(conn, client, table)
            remaining = await conn.fetchval(
                f"SELECT count(*) FROM {table} WHERE embedding IS NULL"
            )
            grand_tokens += tokens
            print(f"{table}: embedded {embedded} chunks, {remaining} still NULL")
        # text-embedding-3-small: $0.02 per 1M tokens
        print(f"total: {grand_tokens} tokens (~${grand_tokens * 0.02 / 1_000_000:.4f})")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
