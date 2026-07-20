"""Shared LLM-boundary helpers used by BOTH approaches: load the per-user
pseudonymizer, gate text behind the PII_MASKING flag, persist newly found
mappings (keeps pii_mappings authoritative for the leakage scan), and log
every LLM-bound payload to llm_payload_log.

pii/pseudonymizer.py stays pure (regex + mapping, no I/O); this module is
its integration layer against the database.
"""

from app.config import settings
from app.db import get_pool
from pii.pseudonymizer import Pseudonymizer


async def load_pseudonymizer(user_id: int) -> Pseudonymizer:
    pool = await get_pool()
    async with pool.acquire() as conn:
        known = {
            m["real_value"]: (m["pii_type"], m["fake_value"])
            for m in await conn.fetch(
                "SELECT pii_type, real_value, fake_value FROM pii_mappings "
                "WHERE user_id = $1",
                user_id,
            )
        }
    return Pseudonymizer(user_id, known)


async def persist_mappings(user_id: int, added: list[tuple[str, str, str]]) -> None:
    if not added:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO pii_mappings (user_id, pii_type, real_value, fake_value) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT (user_id, real_value) DO NOTHING",
            [(user_id, t, real, fake) for t, real, fake in added],
        )


async def gate_text(pseudonymizer: Pseudonymizer, text: str) -> str:
    """Mask text when PII_MASKING is on (no-op when off), persisting any
    newly discovered values. The caller still logs the result."""
    if not settings.pii_masking:
        return text
    added = pseudonymizer.register(text)
    masked = pseudonymizer.pseudonymize(text)
    await persist_mappings(pseudonymizer.user_id, added)
    return masked


async def log_payload(user_id: int, approach: str, kind: str, content: str,
                      direction: str = "to_llm", run_id: str | None = None) -> None:
    """run_id groups every payload one /ask call produced, so the PII
    transparency page can show which rows belong to the same question."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO llm_payload_log (user_id, approach, direction, kind, content, run_id) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            user_id, approach, direction, kind, content, run_id,
        )
