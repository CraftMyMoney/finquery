"""Vanilla RAG baseline tests, key-free: synthetic embeddings planted on a
few chunks (reset to NULL afterwards), fake embed/complete injected, so the
REAL pipeline (retrieval SQL, context assembly, PII gate, payload logging)
runs against the live seeded DB with zero OpenAI calls.
"""

import asyncpg
import pytest

from app.config import settings
from app.db import close_pool, get_pool, ping
from baseline.plain_rag import run_rag
from guardrails.refusal import REFUSAL_MARKER
from retrieval.hybrid import vector_literal

DIMS = 1536


def _unit(axis: int) -> list[float]:
    v = [0.0] * DIMS
    v[axis] = 1.0
    return v


def _fake_embed(vector):
    async def embed(text: str) -> list[float]:
        return vector
    return embed


def _capturing_complete(captured: dict, answer: str = "Answer from context."):
    async def complete(system: str, user: str) -> str:
        captured["system"] = system
        captured["user"] = user
        return answer
    return complete


@pytest.fixture(autouse=True)
async def db_guard():
    """Skip without a DB; clean payload-log rows written by each test."""
    await close_pool()
    if not await ping():
        await close_pool()
        pytest.skip("seeded DB not reachable on DATABASE_URL")
    pool = await get_pool()
    log_before = await pool.fetchval("SELECT coalesce(max(id), 0) FROM llm_payload_log")
    yield
    pool = await get_pool()
    await pool.execute("DELETE FROM llm_payload_log WHERE id > $1", log_before)
    await close_pool()


@pytest.fixture
async def planted():
    """One kb chunk on axis 0, one user-1 txn chunk on axis 1. The vectors must
    be committed (run_rag reads through the pool), so the fixture restores each
    row's prior embedding afterwards instead of assuming it was NULL. Assuming
    NULL silently erodes the embedding backfill one row per run."""
    conn = await asyncpg.connect(settings.database_url)
    kb = await conn.fetchrow(
        "SELECT id, embedding::text AS prior FROM kb_chunks ORDER BY id LIMIT 1")
    txn = await conn.fetchrow(
        "SELECT id, embedding::text AS prior FROM rag_transaction_chunks "
        "WHERE user_id = 1 ORDER BY id LIMIT 1")
    kb_id, txn_id = kb["id"], txn["id"]
    await conn.execute("UPDATE kb_chunks SET embedding = $1::vector WHERE id = $2",
                       vector_literal(_unit(0)), kb_id)
    await conn.execute(
        "UPDATE rag_transaction_chunks SET embedding = $1::vector WHERE id = $2",
        vector_literal(_unit(1)), txn_id)
    yield {"kb_id": kb_id, "txn_id": txn_id, "conn": conn}
    await conn.execute("UPDATE kb_chunks SET embedding = $1::vector WHERE id = $2",
                       kb["prior"], kb_id)
    await conn.execute(
        "UPDATE rag_transaction_chunks SET embedding = $1::vector WHERE id = $2",
        txn["prior"], txn_id)
    await conn.close()


async def test_pipeline_retrieves_both_corpora_and_masks_the_question(planted):
    vpa = await planted["conn"].fetchrow(
        "SELECT real_value, fake_value FROM pii_mappings "
        "WHERE user_id = 1 AND pii_type = 'vpa' LIMIT 1")
    captured: dict = {}

    result = await run_rag(
        f"Did I pay {vpa['real_value']} for groceries?", 1,
        embed=_fake_embed(_unit(1)),  # nearest the txn chunk, kb second
        complete=_capturing_complete(captured),
    )

    assert result.answer == "Answer from context."
    assert result.refused is False and result.tool_calls == []
    # planted txn chunk (distance 0) always ranks first; kb chunks follow.
    # After the real backfill other embedded chunks may fill the remaining
    # slots, so assert kinds, not an exact list.
    kinds = [c.kind for c in result.citations]
    assert kinds[0] == "txn_chunk" and "kb_chunk" in kinds
    assert result.citations[0].detail.startswith("Bank transactions of")

    assert "[1] (your bank transactions)" in captured["user"]
    assert "(knowledge base:" in captured["user"]
    assert vpa["real_value"] not in captured["user"]
    assert vpa["fake_value"] in captured["user"]

    # every LLM-bound payload logged under approach='rag', none with real PII
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT approach, kind, direction, content FROM llm_payload_log "
        "WHERE approach = 'rag' ORDER BY id DESC LIMIT 3")
    assert {(r["kind"], r["direction"]) for r in rows} == {
        ("system", "to_llm"), ("user", "to_llm"), ("answer", "from_llm")}
    reals = [r["real_value"] for r in await planted["conn"].fetch(
        "SELECT real_value FROM pii_mappings WHERE user_id = 1")]
    for r in rows:
        assert not any(real in r["content"] for real in reals)


async def test_other_users_transaction_chunks_are_invisible(planted):
    other = await planted["conn"].fetchrow(
        "SELECT id, embedding::text AS prior FROM rag_transaction_chunks "
        "WHERE user_id = 2 ORDER BY id LIMIT 1")
    other_txn = other["id"]
    await planted["conn"].execute(
        "UPDATE rag_transaction_chunks SET embedding = $1::vector WHERE id = $2",
        vector_literal(_unit(1)), other_txn)
    try:
        captured: dict = {}
        result = await run_rag("What did I spend?", 2,
                               embed=_fake_embed(_unit(1)),
                               complete=_capturing_complete(captured))
        # user 2 sees their own chunk...
        assert f"transaction chunk {other_txn}" in [c.ref for c in result.citations]

        captured2: dict = {}
        result1 = await run_rag("What did I spend?", 1,
                                embed=_fake_embed(_unit(1)),
                                complete=_capturing_complete(captured2))
        # ...user 1 must not, even though it is the nearest vector in the table
        assert f"transaction chunk {other_txn}" not in [c.ref for c in result1.citations]
    finally:
        await planted["conn"].execute(
            "UPDATE rag_transaction_chunks SET embedding = $1::vector WHERE id = $2",
            other["prior"], other_txn)


async def test_without_embeddings_fails_loudly_before_any_api_call():
    conn = await asyncpg.connect(settings.database_url)
    embedded = await conn.fetchval(
        """SELECT (SELECT count(*) FROM kb_chunks WHERE embedding IS NOT NULL)
                + (SELECT count(*) FROM rag_transaction_chunks
                   WHERE user_id = 1 AND embedding IS NOT NULL)""")
    await conn.close()
    if embedded:
        pytest.skip("embeddings are backfilled; the empty-state guard cannot fire")

    async def tripwire(text: str) -> list[float]:
        raise AssertionError("embed must never be called when nothing is embedded")

    with pytest.raises(RuntimeError, match="embed_chunks"):
        await run_rag("anything", 1, embed=tripwire)


async def test_refusal_marker_sets_refused_flag(planted):
    result = await run_rag(
        "Should I buy SBI Small Cap Fund?", 1,
        embed=_fake_embed(_unit(0)),
        complete=_capturing_complete({}, answer=(
            f"{REFUSAL_MARKER}. Picking funds requires a SEBI-registered adviser.")),
    )
    assert result.refused is True


async def test_pii_flag_off_sends_the_raw_question(planted, monkeypatch):
    monkeypatch.setattr(settings, "pii_masking", False)
    vpa_real = await planted["conn"].fetchval(
        "SELECT real_value FROM pii_mappings WHERE user_id = 1 AND pii_type = 'vpa' LIMIT 1")
    captured: dict = {}
    await run_rag(f"Did I pay {vpa_real}?", 1,
                  embed=_fake_embed(_unit(0)),
                  complete=_capturing_complete(captured))
    assert vpa_real in captured["user"]


async def test_question_length_cap():
    with pytest.raises(ValueError, match="exceeds"):
        await run_rag("x" * 1001, 1)
