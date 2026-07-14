"""Precompute ground truth for the golden set by running its SQL against the
seeded DB, and write eval/ground_truth.json (committed artifact).

Ground truth is derived, never hand-typed: every numeric answer comes from a
SQL query stored alongside its question in golden_set.json. Re-run after any
re-seed; the diff on ground_truth.json shows exactly what moved.

Usage: python -m eval.compute_ground_truth
"""

import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import asyncpg

from app.config import settings

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden_set.json"
OUT = HERE / "ground_truth.json"


def _plain(value):
    """Decimal -> str (exact), date -> ISO, passthrough otherwise."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


async def _run_sql(conn, sql: str, answer_type: str):
    if answer_type == "number":
        return _plain(await conn.fetchval(sql))
    if answer_type == "row":
        row = await conn.fetchrow(sql)
        return {k: _plain(v) for k, v in row.items()} if row else None
    if answer_type == "rows":
        return [{k: _plain(v) for k, v in r.items()} for r in await conn.fetch(sql)]
    raise ValueError(f"unknown answer_type: {answer_type}")


async def main() -> None:
    golden = json.loads(GOLDEN.read_text())
    conn = await asyncpg.connect(settings.database_url)
    truth: dict[str, dict] = {}
    try:
        for q in golden["questions"]:
            qid, bucket = q["id"], q["bucket"]
            if bucket in ("aggregation", "lookup"):
                value = await _run_sql(conn, q["ground_truth_sql"], q["answer_type"])
                if value is None:
                    raise SystemExit(f"{qid}: SQL returned NULL; seed data and question disagree")
                truth[qid] = {"bucket": bucket, "value": value}
            elif bucket == "composite":
                components = {}
                for comp in q["components"]:
                    value = await _run_sql(conn, comp["sql"], comp["answer_type"])
                    if value in (None, []):
                        raise SystemExit(f"{qid}/{comp['name']}: SQL returned nothing")
                    components[comp["name"]] = value
                truth[qid] = {"bucket": bucket, "components": components}
            elif bucket == "refusal":
                truth[qid] = {"bucket": bucket, "expect_refusal": True}
            elif bucket == "education":
                # judge-scored against expected_points; no SQL ground truth
                truth[qid] = {"bucket": bucket, "expected_source": q["expected_source"]}
    finally:
        await conn.close()

    OUT.write_text(json.dumps(truth, indent=2) + "\n")
    by_bucket: dict[str, int] = {}
    for t in truth.values():
        by_bucket[t["bucket"]] = by_bucket.get(t["bucket"], 0) + 1
    print(f"wrote {OUT.name}: {len(truth)} questions {by_bucket}")


if __name__ == "__main__":
    asyncio.run(main())
