"""search_finance_kb — the agent's sixth tool, retrieval over the KB corpus.

Currently sparse-only (Postgres full-text over the tsv GIN index): the dense
leg needs embeddings, which wait on the OpenAI key. When retrieval/hybrid.py
lands, this tool switches to dense or hybrid-RRF per the eval ablation; the
typed result already carries retrieval_mode so logged runs stay comparable.

The KB is shared public educational material (no user data), so there is no
user_id parameter; the PII gate still runs on the output at the agent
boundary for uniformity of the leakage scan.
"""

from pydantic_ai import ModelRetry

from app.db import get_pool
from agent.schemas import KBChunkHit, KBSearchResult

RETRIEVAL_MODE = "sparse"


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

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.id, c.content, c.page_ref, d.title, d.publisher,
                   ts_rank_cd(c.tsv, plainto_tsquery('english', $1)) AS rank
            FROM kb_chunks c
            JOIN kb_documents d ON d.id = c.document_id
            WHERE c.tsv @@ plainto_tsquery('english', $1)
            ORDER BY rank DESC
            LIMIT $2
            """,
            query, limit,
        )

    return KBSearchResult(
        query=query,
        retrieval_mode=RETRIEVAL_MODE,
        hits=[
            KBChunkHit(
                chunk_id=r["id"], document_title=r["title"],
                publisher=r["publisher"], page_ref=r["page_ref"],
                content=r["content"],
            )
            for r in rows
        ],
    )
