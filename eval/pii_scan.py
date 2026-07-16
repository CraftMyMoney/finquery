"""Deterministic PII leakage scan. No judge, no sampling: every logged
LLM-bound payload is substring-matched against EVERY real value in
pii_mappings (cross-user on purpose: another user's value appearing would be
a worse bug than your own).

The 0%-leakage claim is scoped honestly: this scan proves no MAPPED real
value crossed the boundary. Values the detector never knew about are invisible
to it; that residual risk is the detector-recall story in the README
(Failure Analysis entry 8), not something this scan can measure.

With PII_MASKING=false the gate is off, so leaks are EXPECTED: the scan then
serves as its own positive control (it must find them), never as a pass.

Usage:
    python -m eval.pii_scan [--since-id N]
"""

import argparse
import asyncio

import asyncpg

from app.config import settings

_SCAN_SQL = """
SELECT p.id AS payload_id, p.user_id AS payload_user, p.approach, p.direction,
       p.kind, m.user_id AS pii_owner, m.pii_type, m.real_value
FROM llm_payload_log p
JOIN pii_mappings m ON position(m.real_value IN p.content) > 0
WHERE p.id > $1
ORDER BY p.id
"""


async def scan(conn: asyncpg.Connection, since_id: int = 0) -> list[asyncpg.Record]:
    """All (payload, real value) hits in rows with id > since_id."""
    return await conn.fetch(_SCAN_SQL, since_id)


async def payload_count(conn: asyncpg.Connection, since_id: int = 0) -> int:
    return await conn.fetchval(
        "SELECT count(*) FROM llm_payload_log WHERE id > $1", since_id)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since-id", type=int, default=0,
                        help="only scan llm_payload_log rows with id > N")
    args = parser.parse_args()

    conn = await asyncpg.connect(settings.database_url)
    try:
        scanned = await payload_count(conn, args.since_id)
        leaks = await scan(conn, args.since_id)
    finally:
        await conn.close()

    print(f"scanned {scanned} payloads (id > {args.since_id}), "
          f"{len(leaks)} real-PII hits")
    for leak in leaks:
        print(f"  payload {leak['payload_id']} ({leak['approach']}/{leak['kind']}/"
              f"{leak['direction']}, user {leak['payload_user']}): "
              f"{leak['pii_type']} of user {leak['pii_owner']}: {leak['real_value']!r}")

    if settings.pii_masking:
        if leaks:
            raise SystemExit("FAIL: real PII crossed the LLM boundary with the gate ON")
        print("PASS: 0 mapped real values in any LLM-bound payload")
    else:
        if leaks:
            print("EXPECTED-POSITIVE: gate is off (PII_MASKING=false) and the "
                  "scan found the raw values, proving it works. Not a pass.")
        elif scanned:
            print("NOTE: gate is off but no leaks found; either these payloads "
                  "carried no PII or something is masking unexpectedly.")


if __name__ == "__main__":
    asyncio.run(main())
