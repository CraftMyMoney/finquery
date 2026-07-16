"""search_finance_kb — the agent's sixth tool, retrieval over the KB corpus.

The retrieval leg is picked by KB_RETRIEVAL_MODE (settings), NOT by the
model: sparse (key-free, tsv GIN index), dense (pgvector cosine), or hybrid
(dense + sparse merged with RRF). That makes the agent+dense vs agent+hybrid
eval ablation a config flip, and keeps the typed result self-describing via
retrieval_mode so logged runs stay comparable.

The KB is shared public educational material (no user data), so there is no
user_id parameter; the PII gate still runs on the output at the agent
boundary for uniformity of the leakage scan.
"""

from pydantic_ai import ModelRetry

from app.config import settings
from app.db import get_pool
from agent.schemas import KBChunkHit, KBSearchResult
from retrieval.hybrid import (
    dense_ranking,
    embed_query,
    fetch_chunks,
    hybrid_ranking,
    sparse_ranking,
)


async def search_finance_kb(query: str, limit: int = 5) -> KBSearchResult:
    """Search the personal-finance knowledge base (RBI/NCFE investor-education
    material and original articles) for concepts, rules of thumb, and how
    financial products work.

    Args:
        query: What to look up, e.g. 'emergency fund size' or '50/30/20 rule'.
        limit: Max chunks to return (1-10, default 5).
    """
    if not query.strip():
        raise ModelRetry("query is empty; pass the concept to look up.")
    limit = max(1, min(limit, 10))
    mode = settings.kb_retrieval_mode

    pool = await get_pool()
    async with pool.acquire() as conn:
        if mode == "sparse":
            ids = (await sparse_ranking(conn, query))[:limit]
        elif mode == "dense":
            ids = (await dense_ranking(conn, await embed_query(query)))[:limit]
        elif mode == "hybrid":
            ids = await hybrid_ranking(conn, query, await embed_query(query), limit)
        else:
            raise RuntimeError(
                f"KB_RETRIEVAL_MODE={mode!r} is not valid; use sparse, dense, or hybrid"
            )
        rows = await fetch_chunks(conn, ids)

    return KBSearchResult(
        query=query,
        retrieval_mode=mode,
        hits=[
            KBChunkHit(
                chunk_id=r["id"], document_title=r["title"],
                publisher=r["publisher"], page_ref=r["page_ref"],
                content=r["content"],
            )
            for r in rows
        ],
    )
