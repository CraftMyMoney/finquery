"""Approach A: vanilla RAG baseline. Deliberately simple, that is the point.

One dense retrieval over BOTH corpora (kb_chunks + the user's
rag_transaction_chunks, one pgvector cosine scan each, merged by distance),
chunk TEXT pasted into a single LLM call, no tools, no loop. The comparative
eval hypothesis is that this fails on aggregations: totals require every
relevant transaction line to land in the top-k AND the LLM to sum them
correctly. Nothing here helps it cheat (no precomputed sums, no SQL), and
the prompt explicitly allows computing from the context so the failure is
capability, not instruction-following.

PII: transaction chunks are pseudonymized at rest (serializer gate); the
question passes the same gate_text as approach B. Every LLM-bound payload
is logged to llm_payload_log with approach='rag'. The query embedding call
also crosses the LLM boundary, so it embeds the MASKED question.

The two OpenAI calls (embed, complete) are injectable, so the whole pipeline
is testable before the key arrives.
"""

import time

import asyncpg

from app.config import settings
from app.db import get_pool
from app.schemas import Citation, RunResult
from guardrails.refusal import REFUSAL_CRITERIA, is_refusal
from pii.boundary import gate_text, load_pseudonymizer, log_payload
from retrieval.hybrid import embed_query, vector_literal

TOP_K = 8                   # ~400-token chunks -> ~3200 tokens of context
MAX_QUESTION_CHARS = 1000   # mirrors AskRequest, same as the agent

SYSTEM_PROMPT = f"""\
You are FinQuery, a grounded personal-finance assistant for a user in India. \
Amounts are Indian Rupees (INR).

Answer using ONLY the context provided in the user message: knowledge-base \
passages and lines from the user's own bank transactions. Do not use outside \
knowledge for facts or numbers. When a question asks for a total, count, or \
comparison, compute it from the transaction lines present in the context. If \
the context does not contain the information needed, say so plainly instead \
of guessing. Keep answers short and factual.

{REFUSAL_CRITERIA}"""

_RETRIEVE_SQL = """
SELECT * FROM (
    SELECT 'kb' AS source, c.id, c.content, d.title, c.page_ref,
           c.embedding <=> $1::vector AS dist
    FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id
    WHERE c.embedding IS NOT NULL
    UNION ALL
    SELECT 'txn', t.id, t.content, NULL, NULL,
           t.embedding <=> $1::vector
    FROM rag_transaction_chunks t
    WHERE t.user_id = $2 AND t.embedding IS NOT NULL
) merged
ORDER BY dist, source, id
LIMIT $3
"""


async def _complete_live(system: str, user: str) -> str:
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is empty in .env; pass a fake complete() or configure the key."
        )
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.llm_model,
        temperature=0,  # eval reproducibility
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
    )
    return response.choices[0].message.content or ""


def _build_context(rows: list[asyncpg.Record]) -> tuple[str, list[Citation]]:
    blocks: list[str] = []
    citations: list[Citation] = []
    for i, r in enumerate(rows, start=1):
        if r["source"] == "kb":
            page = f", {r['page_ref']}" if r["page_ref"] else ""
            blocks.append(f"[{i}] (knowledge base: {r['title']}{page})\n{r['content']}")
            citations.append(Citation(
                kind="kb_chunk", ref=f"{r['title']} (chunk {r['id']})",
                detail=r["page_ref"] or ""))
        else:
            header = r["content"].splitlines()[0]
            blocks.append(f"[{i}] (your bank transactions)\n{r['content']}")
            citations.append(Citation(
                kind="txn_chunk", ref=f"transaction chunk {r['id']}", detail=header))
    return "Context:\n\n" + "\n\n".join(blocks), citations


async def run_rag(question: str, user_id: int, *,
                  embed=None, complete=None) -> RunResult:
    """Answer one question for one user. embed/complete are injected by tests;
    None means the live OpenAI calls."""
    if not question.strip():
        raise ValueError("question is empty")
    if len(question) > MAX_QUESTION_CHARS:
        raise ValueError(f"question exceeds {MAX_QUESTION_CHARS} characters")
    embed = embed or embed_query
    complete = complete or _complete_live

    pool = await get_pool()
    async with pool.acquire() as conn:
        embedded = await conn.fetchval(
            """SELECT (SELECT count(*) FROM kb_chunks WHERE embedding IS NOT NULL)
                    + (SELECT count(*) FROM rag_transaction_chunks
                       WHERE user_id = $1 AND embedding IS NOT NULL)""",
            user_id,
        )
    if embedded == 0:
        raise RuntimeError(
            "no embedded chunks; run 'python -m ingest.embed_chunks' first"
        )

    pseudonymizer = await load_pseudonymizer(user_id)
    question = await gate_text(pseudonymizer, question)

    query_vector = await embed(question)  # embeds the MASKED question
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _RETRIEVE_SQL, vector_literal(query_vector), user_id, TOP_K)
    context, citations = _build_context(rows)
    user_message = f"{context}\n\nQuestion: {question}"

    await log_payload(user_id, "rag", "system", SYSTEM_PROMPT)
    await log_payload(user_id, "rag", "user", user_message)

    started = time.monotonic()
    answer = await complete(SYSTEM_PROMPT, user_message)
    latency_ms = int((time.monotonic() - started) * 1000)

    await log_payload(user_id, "rag", "answer", answer, direction="from_llm")

    return RunResult(
        answer=answer,
        refused=is_refusal(answer),
        citations=citations,
        tool_calls=[],
        latency_ms=latency_ms,
    )
