"""spending_by_category — the aggregation workhorse.

Sums live in SQL, never in the model: an LLM adding 95 grocery rows is exactly
the failure mode the vanilla-RAG baseline is hypothesized to show. The
breakdown drills one level below whatever filter was given, so the agent can
narrate composition ("mostly Fuel") without a second call.
"""

from app.db import get_pool
from agent.schemas import BreakdownRow, SpendingSummary
from agent.tools._validation import DATA_END, DATA_START, parse_date, resolve_taxonomy

_GROUP_BELOW = {None: "category", "category": "subcategory", "subcategory": "spend_type"}


async def spending_by_category(
    user_id: int,
    category: str | None = None,
    subcategory: str | None = None,
    spend_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> SpendingSummary:
    """Total debit spending for a user, optionally filtered by taxonomy and dates.

    Args:
        user_id: The user whose transactions to aggregate.
        category: Optional category name (Essentials, Lifestyle, Goals).
        subcategory: Optional subcategory name, e.g. 'Groceries', 'EMI', 'Travel'.
        spend_type: Optional spend type name, e.g. 'Fuel', 'Mutual Funds'.
        start_date: ISO date YYYY-MM-DD; defaults to the start of available data.
        end_date: ISO date YYYY-MM-DD, inclusive; defaults to the end of available data.
    """
    start = parse_date(start_date, "start_date", DATA_START)
    end = parse_date(end_date, "end_date", DATA_END)

    pool = await get_pool()
    async with pool.acquire() as conn:
        cat_id, sub_id, spend_id = await resolve_taxonomy(conn, category, subcategory, spend_type)

        where = ["t.user_id = $1", "t.txn_type = 'debit'", "t.txn_date >= $2", "t.txn_date <= $3"]
        params: list = [user_id, start, end]
        for col, val in (("category_id", cat_id), ("subcategory_id", sub_id), ("spend_type_id", spend_id)):
            if val is not None:
                params.append(val)
                where.append(f"t.{col} = ${len(params)}")
        where_sql = " AND ".join(where)

        total_row = await conn.fetchrow(
            f"SELECT coalesce(sum(t.amount), 0) AS total, count(*) AS n FROM transactions t WHERE {where_sql}",
            *params,
        )

        # Drill one level below the narrowest filter given.
        narrowest = "subcategory" if spend_id or sub_id else ("category" if cat_id else None)
        breakdown: list[BreakdownRow] = []
        grouped_by = _GROUP_BELOW.get(narrowest, "none")
        if spend_id is None:
            group_table = {"category": "categories c ON c.id = t.category_id",
                           "subcategory": "subcategories c ON c.id = t.subcategory_id",
                           "spend_type": "spend_types c ON c.id = t.spend_type_id"}[grouped_by]
            rows = await conn.fetch(
                f"""SELECT c.name, sum(t.amount) AS total, count(*) AS n
                    FROM transactions t JOIN {group_table}
                    WHERE {where_sql} GROUP BY c.name ORDER BY total DESC""",
                *params,
            )
            breakdown = [BreakdownRow(name=r["name"], total=r["total"], txn_count=r["n"]) for r in rows]
        else:
            grouped_by = "none"

    filters = {k: v for k, v in
               (("category", category), ("subcategory", subcategory), ("spend_type", spend_type)) if v}
    return SpendingSummary(
        start_date=start, end_date=end, filters=filters,
        total=total_row["total"], txn_count=total_row["n"],
        grouped_by=grouped_by, breakdown=breakdown,
    )
