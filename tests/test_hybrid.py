"""Hybrid retrieval tests, all key-free: the RRF merge is pure rank
arithmetic; the ranking legs run against the live DB, the dense leg with
synthetic unit vectors planted on a few chunks and reset to NULL afterwards
(the real backfill is idempotent over NULLs, so this leaves nothing behind).
"""

import math

import asyncpg
import pytest

from app.config import settings
from retrieval.hybrid import (
    RRF_K,
    dense_ranking,
    embed_query,
    fetch_chunks,
    hybrid_ranking,
    rrf_merge,
    sparse_ranking,
    vector_literal,
)

DIMS = 1536


def _unit(axis: int, lean_axis: int | None = None, lean: float = 0.0) -> list[float]:
    """A unit vector along one axis, optionally leaned toward another."""
    v = [0.0] * DIMS
    if lean_axis is None:
        v[axis] = 1.0
    else:
        v[axis] = math.sqrt(1 - lean * lean)
        v[lean_axis] = lean
    return v


# ---------------------------------------------------------------- pure merge

def test_chunk_in_both_legs_beats_single_leg_winners():
    assert rrf_merge([[1, 2, 3], [2, 4, 5]])[0] == 2


def test_scores_follow_the_rrf_formula():
    # chunk 1: rank 1 in one leg -> 1/(k+1); chunk 2: rank 2 + rank 1 -> more
    merged = rrf_merge([[1, 2], [2]])
    assert merged == [2, 1]
    assert 1 / (RRF_K + 2) + 1 / (RRF_K + 1) > 1 / (RRF_K + 1)


def test_equal_scores_break_ties_on_lower_id():
    assert rrf_merge([[7], [3]]) == [3, 7]
    assert rrf_merge([[3], [7]]) == [3, 7]


def test_empty_legs_merge_to_empty():
    assert rrf_merge([[], []]) == []


# ------------------------------------------------------------------ DB legs

@pytest.fixture
async def conn():
    try:
        connection = await asyncpg.connect(settings.database_url)
    except Exception:
        pytest.skip("seeded DB not reachable on DATABASE_URL")
    yield connection
    await connection.close()


async def test_sparse_ranking_finds_the_emergency_fund_chunk(conn):
    ids = await sparse_ranking(conn, "how many months of expenses in an emergency fund")
    assert ids
    rows = await fetch_chunks(conn, ids[:3])
    assert any("emergency" in r["content"].lower() for r in rows)


async def test_fetch_chunks_preserves_ranking_order(conn):
    ids = await sparse_ranking(conn, "mutual fund")
    rows = await fetch_chunks(conn, ids[:5])
    assert [r["id"] for r in rows] == ids[:5]


async def test_dense_ranking_orders_by_cosine_distance(conn):
    # everything runs inside a rolled-back transaction, so the test is
    # deterministic whether or not the real backfill has run, and leaves
    # every embedding exactly as it found it
    tr = conn.transaction()
    await tr.start()
    try:
        await conn.execute("UPDATE kb_chunks SET embedding = NULL")
        planted = [r["id"] for r in await conn.fetch(
            "SELECT id FROM kb_chunks ORDER BY id LIMIT 3")]
        for axis, chunk_id in enumerate(planted):
            await conn.execute(
                "UPDATE kb_chunks SET embedding = $1::vector WHERE id = $2",
                vector_literal(_unit(axis)), chunk_id)

        ranked = await dense_ranking(conn, _unit(1))
        assert ranked[0] == planted[1]
        # only rows WITH embeddings participate; the NULLed rest stay invisible
        assert set(ranked) == set(planted)
    finally:
        await tr.rollback()


async def test_hybrid_promotes_the_chunk_both_legs_agree_on(conn):
    tr = conn.transaction()
    await tr.start()
    try:
        await conn.execute("UPDATE kb_chunks SET embedding = NULL")
        sparse_ids = await sparse_ranking(conn, "how many months of expenses in an emergency fund")
        both_legs = sparse_ids[0]                # sparse winner, gets a dense vector too
        dense_only = await conn.fetchval(
            "SELECT id FROM kb_chunks WHERE id <> $1 ORDER BY id LIMIT 1", both_legs)
        # dense leg alone prefers dense_only (exact match) over both_legs (leaned)
        await conn.execute("UPDATE kb_chunks SET embedding = $1::vector WHERE id = $2",
                           vector_literal(_unit(0)), dense_only)
        await conn.execute("UPDATE kb_chunks SET embedding = $1::vector WHERE id = $2",
                           vector_literal(_unit(1, lean_axis=0, lean=0.6)), both_legs)

        query_vec = _unit(0)
        assert (await dense_ranking(conn, query_vec))[0] == dense_only
        # ...but rank 2 dense + rank 1 sparse beats rank 1 dense alone
        merged = await hybrid_ranking(
            conn, "how many months of expenses in an emergency fund", query_vec, 5)
        assert merged[0] == both_legs
        assert dense_only in merged
    finally:
        await tr.rollback()


# ------------------------------------------------------------- mode routing

async def test_tool_routes_by_settings_mode(conn, monkeypatch):
    from importlib import import_module

    from agent.tools import search_finance_kb
    from app.db import close_pool

    # the package re-exports the function under the module's name, so the
    # module object must come from import_module, not attribute lookup
    kb_module = import_module("agent.tools.search_finance_kb")

    await close_pool()
    monkeypatch.setattr(settings, "kb_retrieval_mode", "hybrid")
    monkeypatch.setattr(kb_module, "embed_query", _fake_embed)
    planted = await conn.fetchval("SELECT id FROM kb_chunks ORDER BY id LIMIT 1")
    try:
        await conn.execute("UPDATE kb_chunks SET embedding = $1::vector WHERE id = $2",
                           vector_literal(_unit(0)), planted)
        result = await search_finance_kb("emergency fund")
        assert result.retrieval_mode == "hybrid"
        assert planted in [h.chunk_id for h in result.hits]
    finally:
        await conn.execute("UPDATE kb_chunks SET embedding = NULL WHERE id = $1", planted)
        await close_pool()


async def _fake_embed(query: str) -> list[float]:
    return _unit(0)


async def test_invalid_mode_fails_loudly(monkeypatch):
    from agent.tools import search_finance_kb
    monkeypatch.setattr(settings, "kb_retrieval_mode", "bm42")
    with pytest.raises(RuntimeError, match="KB_RETRIEVAL_MODE"):
        await search_finance_kb("anything")


async def test_embed_query_refuses_without_key(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        await embed_query("emergency fund")
