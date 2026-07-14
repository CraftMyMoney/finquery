"""Load fake-data/*.csv into transactions and build per-user pii_mappings.

Idempotent by truncate-and-reload of the two tables this script owns
(transactions, pii_mappings); master data is owned by db/seed_master.sql.

Usage: python -m ingest.seed_transactions
"""

import asyncio
import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import asyncpg

from app.config import settings
from pii.pseudonymizer import Pseudonymizer

ROOT = Path(__file__).resolve().parent.parent
CSVS = sorted((ROOT / "fake-data").glob("user*_transactions.csv"))


async def load_lookups(conn) -> tuple[dict, dict, dict, dict]:
    users = {r["username"]: r["id"] for r in await conn.fetch("SELECT id, username FROM users")}
    cats = {r["name"]: r["id"] for r in await conn.fetch("SELECT id, name FROM categories")}
    subs = {
        (r["category_id"], r["name"]): r["id"]
        for r in await conn.fetch("SELECT id, category_id, name FROM subcategories")
    }
    spends = {
        (r["subcategory_id"], r["name"]): r["id"]
        for r in await conn.fetch("SELECT id, subcategory_id, name FROM spend_types")
    }
    return users, cats, subs, spends


async def main() -> None:
    conn = await asyncpg.connect(settings.database_url)
    try:
        users, cats, subs, spends = await load_lookups(conn)
        if not users or not cats:
            raise SystemExit("master data missing; run: python -m ingest.apply_schema --with-master")

        await conn.execute("TRUNCATE transactions, pii_mappings RESTART IDENTITY")

        for path in CSVS:
            username = path.name.split("_")[0]
            user_id = users[username]
            pseudo = Pseudonymizer(user_id)
            rows = []
            with path.open() as f:
                for r in csv.DictReader(f):
                    cat_id = cats[r["category"]] if r["category"] else None
                    sub_id = subs[(cat_id, r["subcategory"])] if r["subcategory"] else None
                    spend_id = spends[(sub_id, r["spend_type"])] if r["spend_type"] else None
                    pseudo.register(r["bank_description"])
                    rows.append((
                        user_id, date.fromisoformat(r["date"]), r["bank_description"],
                        Decimal(r["amount"]), r["type"], cat_id, sub_id, spend_id,
                    ))

            await conn.executemany(
                """INSERT INTO transactions
                   (user_id, txn_date, bank_description, amount, txn_type,
                    category_id, subcategory_id, spend_type_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                rows,
            )
            await conn.executemany(
                """INSERT INTO pii_mappings (user_id, pii_type, real_value, fake_value)
                   VALUES ($1, $2, $3, $4)""",
                [(user_id, t, real, fake) for real, (t, fake) in pseudo.mapping.items()],
            )
            by_type = {}
            for _real, (t, _fake) in pseudo.mapping.items():
                by_type[t] = by_type.get(t, 0) + 1
            print(f"{username}: {len(rows)} transactions, {len(pseudo.mapping)} pii mappings {by_type}")

        total = await conn.fetchval("SELECT count(*) FROM transactions")
        print(f"total transactions: {total}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
