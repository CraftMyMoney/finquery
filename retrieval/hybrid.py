"""Hybrid retrieval: dense (pgvector cosine, exact/flat scan) + sparse
(Postgres full-text ts_rank_cd; honestly named, it is not true BM25), merged
with Reciprocal Rank Fusion. Evaluated as an ablation against dense-only.

RRF: score(chunk) = sum over legs of 1 / (k + rank). k=60 is the standard
constant from the original RRF paper; a ~350-chunk corpus gives no reason to
tune it. The merge works on ranks, not scores, so the incomparable scales of
cosine distance and ts_rank_cd never need calibrating.

The merge and the sparse leg are key-free. The dense leg needs embeddings;
its SQL is integration-tested with synthetic vectors before the key arrives.
"""

from typing import Sequence

import asyncpg

from app.config import settings

RRF_K = 60
CANDIDATE_DEPTH = 30  # per-leg candidate pool fed into the merge


def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(str(v) for v in values) + "]"


def rrf_merge(rankings: Sequence[Sequence[int]], k: int = RRF_K) -> list[int]:
    """Merge ranked id lists (best first) into one list, best first.
    Ties break on lower id so results are deterministic."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))


async def sparse_ranking(conn: asyncpg.Connection, query: str,
                         depth: int = CANDIDATE_DEPTH) -> list[int]:
    rows = await conn.fetch(
        """SELECT id FROM kb_chunks
           WHERE tsv @@ plainto_tsquery('english', $1)
           ORDER BY ts_rank_cd(tsv, plainto_tsquery('english', $1)) DESC, id
           LIMIT $2""",
        query, depth,
    )
    return [r["id"] for r in rows]


async def dense_ranking(conn: asyncpg.Connection, embedding: Sequence[float],
                        depth: int = CANDIDATE_DEPTH) -> list[int]:
    rows = await conn.fetch(
        """SELECT id FROM kb_chunks
           WHERE embedding IS NOT NULL
           ORDER BY embedding <=> $1::vector, id
           LIMIT $2""",
        vector_literal(embedding), depth,
    )
    return [r["id"] for r in rows]


async def hybrid_ranking(conn: asyncpg.Connection, query: str,
                         embedding: Sequence[float], limit: int) -> list[int]:
    return rrf_merge([
        await dense_ranking(conn, embedding),
        await sparse_ranking(conn, query),
    ])[:limit]


async def fetch_chunks(conn: asyncpg.Connection, ids: Sequence[int]) -> list[asyncpg.Record]:
    """Hydrate ranked ids into chunk rows, preserving the given order."""
    if not ids:
        return []
    rows = await conn.fetch(
        """SELECT c.id, c.content, c.page_ref, d.title, d.publisher
           FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id
           WHERE c.id = ANY($1)""",
        list(ids),
    )
    by_id = {r["id"]: r for r in rows}
    return [by_id[i] for i in ids if i in by_id]


async def embed_query(text: str) -> list[float]:
    """One query embedding (key-dependent; only dense/hybrid modes call it)."""
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is empty in .env; dense/hybrid retrieval needs it. "
            "Set KB_RETRIEVAL_MODE=sparse to stay key-free."
        )
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.embeddings.create(
        model=settings.embedding_model, input=[text]
    )
    return response.data[0].embedding
