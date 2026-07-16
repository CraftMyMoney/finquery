"""Leakage-scan tests: the scan must find a planted real value (positive
control), stay quiet on properly masked content, and respect the watermark.
Planted rows are deleted afterwards."""

import asyncpg
import pytest

from app.config import settings
from eval.pii_scan import payload_count, scan


@pytest.fixture
async def conn():
    try:
        connection = await asyncpg.connect(settings.database_url)
    except Exception:
        pytest.skip("seeded DB not reachable on DATABASE_URL")
    watermark = await connection.fetchval(
        "SELECT coalesce(max(id), 0) FROM llm_payload_log")
    yield connection, watermark
    await connection.execute("DELETE FROM llm_payload_log WHERE id > $1", watermark)
    await connection.close()


async def _insert(conn, content: str) -> None:
    await conn.execute(
        "INSERT INTO llm_payload_log (user_id, approach, direction, kind, content) "
        "VALUES (1, 'agent', 'to_llm', 'tool_result', $1)", content)


async def test_scan_finds_a_planted_real_value(conn):
    db, watermark = conn
    mapping = await db.fetchrow(
        "SELECT pii_type, real_value FROM pii_mappings WHERE user_id = 1 LIMIT 1")
    await _insert(db, f"paid via {mapping['real_value']} yesterday")

    leaks = await scan(db, watermark)
    assert len(leaks) == 1
    assert leaks[0]["real_value"] == mapping["real_value"]
    assert leaks[0]["pii_type"] == mapping["pii_type"]
    assert leaks[0]["pii_owner"] == 1
    assert await payload_count(db, watermark) == 1


async def test_masked_content_is_clean(conn):
    db, watermark = conn
    fake = await db.fetchval(
        "SELECT fake_value FROM pii_mappings WHERE user_id = 1 AND pii_type = 'vpa' LIMIT 1")
    await _insert(db, f"paid via {fake} yesterday")
    assert await scan(db, watermark) == []


async def test_cross_user_values_are_caught(conn):
    db, watermark = conn
    other = await db.fetchval(
        "SELECT real_value FROM pii_mappings WHERE user_id = 2 LIMIT 1")
    await _insert(db, f"user 1 payload somehow containing {other}")
    leaks = await scan(db, watermark)
    assert len(leaks) == 1 and leaks[0]["pii_owner"] == 2


async def test_watermark_scopes_the_scan(conn):
    db, watermark = conn
    real = await db.fetchval(
        "SELECT real_value FROM pii_mappings WHERE user_id = 1 LIMIT 1")
    await _insert(db, f"old row with {real}")
    new_watermark = await db.fetchval("SELECT max(id) FROM llm_payload_log")
    assert await scan(db, new_watermark) == []          # planted row is behind it
    assert len(await scan(db, watermark)) == 1          # still visible from before
