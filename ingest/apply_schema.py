"""Apply db/schema.sql (DDL) and optionally db/seed_master.sql (master DML).

Both files are idempotent, so re-running after edits is safe. Shape changes to
existing tables are handled by drop + re-seed instead of migrations (recorded
decision: Alembic rejected for a re-seedable synthetic DB).

Usage:
    python -m ingest.apply_schema             # schema only
    python -m ingest.apply_schema --with-master
"""

import asyncio
import sys
from pathlib import Path

import asyncpg

from app.config import settings

ROOT = Path(__file__).resolve().parent.parent


async def main(with_master: bool) -> None:
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute((ROOT / "db" / "schema.sql").read_text())
        print("applied db/schema.sql")
        if with_master:
            await conn.execute((ROOT / "db" / "seed_master.sql").read_text())
            counts = {}
            for table in ("categories", "subcategories", "spend_types", "users", "budgets"):
                counts[table] = await conn.fetchval(f"SELECT count(*) FROM {table}")
            print("applied db/seed_master.sql:", counts)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main(with_master="--with-master" in sys.argv))
