"""Transaction serializer tests: pure packer unit tests plus DB round-trip
checks for the two guarantees Approach A depends on: every transaction lands
in exactly one chunk (clean partition), and no real PII value is stored."""

from datetime import date
from decimal import Decimal

import asyncpg
import pytest

from app.config import settings
from ingest.serialize_transactions import load, serialize_rows
from retrieval.chunking import TARGET_TOKENS, count_tokens


def _row(i: int, d: date, desc: str = "POS 416021XXXXXX8907 DMART") -> dict:
    return {
        "id": i, "txn_date": d, "txn_type": "debit",
        "amount": Decimal("100.00"), "bank_description": desc,
        "category": "Essentials", "subcategory": "Groceries",
        "spend_type": "Supermarket",
    }


# ---------------------------------------------------------------- pure packer

def test_rows_partition_cleanly_with_part_headers():
    rows = [_row(i, date(2026, 3, 1 + i % 28)) for i in range(60)]
    rows += [_row(100 + i, date(2026, 4, 1 + i % 28)) for i in range(5)]
    chunks = serialize_rows(rows, "user1")

    seen: list[int] = []
    for content, ids in chunks:
        assert content.startswith("Bank transactions of user1 for ")
        assert count_tokens(content) <= TARGET_TOKENS + 10
        assert len(ids) == len(content.splitlines()) - 1  # header + 1 line per txn
        seen += ids
    assert sorted(seen) == sorted(r["id"] for r in rows)  # no dupes, none missing

    march = [c for c, _ in chunks if "March 2026" in c]
    april = [c for c, _ in chunks if "April 2026" in c]
    assert len(march) > 1 and f"part 1 of {len(march)}" in march[0]
    assert len(april) == 1 and "part 1 of 1" in april[0]


def test_credit_without_category_uses_dash_path():
    row = _row(1, date(2026, 1, 1), desc="NEFT CR-HDFC0000123-TECHNOVA-SALARY")
    row.update(txn_type="credit", category=None, subcategory=None, spend_type=None)
    content, ids = serialize_rows([row], "user1")[0]
    assert "| credit | 100.00 | - | NEFT CR-" in content and ids == [1]


# ---------------------------------------------------------------- DB round trip

async def test_load_partitions_all_users_and_stores_no_real_pii(monkeypatch):
    monkeypatch.setattr(settings, "pii_masking", True)
    try:
        conn = await asyncpg.connect(settings.database_url)
    except Exception:
        pytest.skip("seeded DB not reachable on DATABASE_URL")
    # load() wipes rag_transaction_chunks, so keep it inside a rolled-back
    # transaction; otherwise the run discards the embedding backfill
    tr = conn.transaction()
    await tr.start()
    try:
        counts = await load(conn)
        assert await load(conn) == counts  # idempotent wipe-and-reload

        # clean partition per user: chunk ids == transaction ids, exactly once
        for user_id in (1, 2, 3):
            chunk_ids = [
                i for r in await conn.fetch(
                    "SELECT source_txn_ids FROM rag_transaction_chunks WHERE user_id = $1",
                    user_id)
                for i in r["source_txn_ids"]
            ]
            txn_ids = [r["id"] for r in await conn.fetch(
                "SELECT id FROM transactions WHERE user_id = $1", user_id)]
            assert sorted(chunk_ids) == sorted(txn_ids)

        # at-rest PII guarantee: no stored chunk contains any real mapped value
        leaks = await conn.fetchval(
            """
            SELECT count(*)
            FROM rag_transaction_chunks c
            JOIN pii_mappings m ON m.user_id = c.user_id
            WHERE position(m.real_value IN c.content) > 0
            """
        )
        assert leaks == 0

        # fake values ARE present (the gate actually ran, not a no-op)
        assert await conn.fetchval(
            "SELECT count(*) FROM rag_transaction_chunks WHERE content LIKE '%@fakeupi%'"
        ) > 0

        assert await conn.fetchval(
            "SELECT count(*) FROM rag_transaction_chunks WHERE embedding IS NOT NULL"
        ) == 0
        assert await conn.fetchval(
            "SELECT count(*) FROM rag_transaction_chunks WHERE tsv IS NULL"
        ) == 0
    finally:
        await tr.rollback()
        await conn.close()


async def test_pii_masking_flag_toggles_the_gate(monkeypatch):
    """PII_MASKING=false stores raw narrations (ablation mode); turning it
    back on restores the pseudonymized state. Rolled back either way, so the
    embedding backfill survives the run."""
    try:
        conn = await asyncpg.connect(settings.database_url)
    except Exception:
        pytest.skip("seeded DB not reachable on DATABASE_URL")
    tr = conn.transaction()
    await tr.start()
    try:
        leak_sql = """
            SELECT count(*)
            FROM rag_transaction_chunks c
            JOIN pii_mappings m ON m.user_id = c.user_id
            WHERE position(m.real_value IN c.content) > 0
        """
        monkeypatch.setattr(settings, "pii_masking", False)
        await load(conn)
        assert await conn.fetchval(leak_sql) > 0  # raw values present by design

        monkeypatch.setattr(settings, "pii_masking", True)
        await load(conn)
        assert await conn.fetchval(leak_sql) == 0
    finally:
        await tr.rollback()
        await conn.close()
