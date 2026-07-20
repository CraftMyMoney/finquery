"""Shared LLM-boundary helpers used by BOTH approaches: load the per-user
pseudonymizer, gate text behind the PII_MASKING flag, persist newly found
mappings (keeps pii_mappings authoritative for the leakage scan), and log
every LLM-bound payload to llm_payload_log.

pii/pseudonymizer.py stays pure (regex + mapping, no I/O); this module is
its integration layer against the database.
"""

import json

from app.config import settings
from app.db import get_pool
from pii.pseudonymizer import Pseudonymizer

# What gate_text substituted in one payload: [{"type": "vpa", "fake": "..."}].
# Fake values only; real values stay in pii_mappings.
Replacements = list[dict[str, str]]


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


async def gate_text(pseudonymizer: Pseudonymizer, text: str) -> tuple[str, Replacements]:
    """Mask text when PII_MASKING is on (no-op when off), persisting any newly
    discovered values. Returns the masked text and the substitutions applied to
    it; the caller passes the latter to log_payload so the PII page can show,
    per payload, how many values were replaced and of what type.

    With masking off (the ablation) the report is empty, which is the point:
    the log then shows raw values and zero substitutions."""
    if not settings.pii_masking:
        return text, []
    added = pseudonymizer.register(text)
    masked, applied = pseudonymizer.pseudonymize_with_report(text)
    await persist_mappings(pseudonymizer.user_id, added)
    return masked, [{"type": t, "fake": f} for t, f in applied]


async def log_payload(user_id: int, approach: str, kind: str, content: str,
                      direction: str = "to_llm", run_id: str | None = None,
                      replacements: Replacements | None = None) -> None:
    """run_id groups every payload one /ask call produced, so the PII
    transparency page can show which rows belong to the same question.

    replacements records what gate_text substituted in this exact payload, so
    the log is self-evidencing: a reader sees the masking happened rather than
    having to infer it from fake-looking strings."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO llm_payload_log "
            "(user_id, approach, direction, kind, content, run_id, replacements) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            user_id, approach, direction, kind, content, run_id,
            json.dumps(replacements or []),
        )
