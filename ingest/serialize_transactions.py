"""Serialize transactions into rag_transaction_chunks for Approach A.

Each transaction becomes one text line (date | type | amount | category path |
narration); lines are grouped per calendar month and packed into ~400-token
chunks. Chunks are a clean partition, deliberately no overlap: overlapping
windows would duplicate transactions across chunks and corrupt any total the
baseline LLM attempts to compute. No precomputed sums are added either; the
baseline must stay vanilla for the comparative eval to be fair.

Content is pseudonymized BEFORE storage (schema contract), so the embedding
backfill and every retrieval read a PII-clean table. The script self-checks:
if any known real PII value survives into a chunk, it aborts loudly.

PII_MASKING=false in .env skips the gate (chunks stored raw) for the
masked-vs-unmasked ablation; re-run this script after flipping the flag.

Key-independent: embedding stays NULL until the OpenAI key arrives.

Usage:
    python -m ingest.serialize_transactions
"""

import asyncio

import asyncpg

from app.config import settings
from pii.pseudonymizer import Pseudonymizer
from retrieval.chunking import TARGET_TOKENS, count_tokens

_HEADER_BUDGET = 20  # tokens reserved for the part header line


def _line(row) -> str:
    path = " > ".join(
        x for x in (row["category"], row["subcategory"], row["spend_type"]) if x
    ) or "-"
    return (f"{row['txn_date'].isoformat()} | {row['txn_type']} | {row['amount']} "
            f"| {path} | {row['bank_description']}")


def serialize_rows(rows, username: str) -> list[tuple[str, list[int]]]:
    """Pure packer: rows (sorted by date) -> [(chunk_content, source_txn_ids)].
    Rows need txn_date, txn_type, amount, bank_description, category,
    subcategory, spend_type, id keys; dicts or asyncpg Records both work."""
    by_month: dict[str, list] = {}
    for row in rows:
        by_month.setdefault(row["txn_date"].strftime("%B %Y"), []).append(row)

    chunks: list[tuple[str, list[int]]] = []
    for month, month_rows in by_month.items():
        parts: list[list[tuple[str, int]]] = []
        cur: list[tuple[str, int]] = []
        cur_tokens = 0
        for row in month_rows:
            line = _line(row)
            line_tokens = count_tokens(line)
            if cur and cur_tokens + line_tokens > TARGET_TOKENS - _HEADER_BUDGET:
                parts.append(cur)
                cur, cur_tokens = [], 0
            cur.append((line, row["id"]))
            cur_tokens += line_tokens
        if cur:
            parts.append(cur)
        for i, part in enumerate(parts, 1):
            header = (f"Bank transactions of {username} for {month}, "
                      f"part {i} of {len(parts)}:")
            content = header + "\n" + "\n".join(line for line, _ in part)
            chunks.append((content, [txn_id for _, txn_id in part]))
    return chunks


async def load(conn: asyncpg.Connection) -> dict[str, int]:
    """Wipe and reload rag_transaction_chunks for every user. Returns chunk
    counts per username. Raises SystemExit if real PII survives the gate."""
    users = await conn.fetch("SELECT id, username FROM users ORDER BY id")
    counts: dict[str, int] = {}
    async with conn.transaction():
        await conn.execute("DELETE FROM rag_transaction_chunks")
        for user in users:
            rows = await conn.fetch(
                """
                SELECT t.id, t.txn_date, t.bank_description, t.amount, t.txn_type,
                       c.name AS category, s.name AS subcategory, st.name AS spend_type
                FROM transactions t
                LEFT JOIN categories c ON c.id = t.category_id
                LEFT JOIN subcategories s ON s.id = t.subcategory_id
                LEFT JOIN spend_types st ON st.id = t.spend_type_id
                WHERE t.user_id = $1
                ORDER BY t.txn_date, t.id
                """,
                user["id"],
            )
            chunks = serialize_rows(rows, user["username"])
            if settings.pii_masking:
                known = {
                    m["real_value"]: (m["pii_type"], m["fake_value"])
                    for m in await conn.fetch(
                        "SELECT pii_type, real_value, fake_value FROM pii_mappings "
                        "WHERE user_id = $1",
                        user["id"],
                    )
                }
                gate = Pseudonymizer(user["id"], known)

                clean: list[tuple[str, list[int]]] = []
                newly_found: list[tuple[str, str, str]] = []
                for content, txn_ids in chunks:
                    newly_found += gate.register(content)
                    clean.append((gate.pseudonymize(content), txn_ids))

                if newly_found:  # keep pii_mappings authoritative for the leakage scan
                    await conn.executemany(
                        "INSERT INTO pii_mappings (user_id, pii_type, real_value, fake_value) "
                        "VALUES ($1, $2, $3, $4) ON CONFLICT (user_id, real_value) DO NOTHING",
                        [(user["id"], t, real, fake) for t, real, fake in newly_found],
                    )

                for content, _ in clean:
                    for real in gate.mapping:
                        if real in content:
                            raise SystemExit(
                                f"real PII value {real!r} survived into a stored chunk "
                                f"for {user['username']}; aborting"
                            )
            else:
                clean = chunks  # ablation mode: stored raw, gate skipped

            await conn.executemany(
                "INSERT INTO rag_transaction_chunks (user_id, content, source_txn_ids) "
                "VALUES ($1, $2, $3)",
                [(user["id"], content, txn_ids) for content, txn_ids in clean],
            )
            counts[user["username"]] = len(clean)
    return counts


async def main() -> None:
    conn = await asyncpg.connect(settings.database_url)
    try:
        counts = await load(conn)
        for username, n in counts.items():
            print(f"{n:4d}  {username}")
        total = sum(counts.values())
        state = ("pseudonymized at rest" if settings.pii_masking
                 else "RAW at rest (PII_MASKING=false, ablation mode)")
        print(f"\n{total} transaction chunks, {state}, embeddings NULL, pending API key")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
