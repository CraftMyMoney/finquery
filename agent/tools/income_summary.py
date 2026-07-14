"""income_summary — the credit side of the ledger.

Credits are few (salary, interest, refunds), so the full rows are returned
alongside the totals: "when did my salary land" and "what was my total income
in March" are both answered from one call, with every amount SQL-exact.
"""

from app.db import get_pool
from agent.schemas import IncomeSummary, MonthTotal, TransactionRow
from agent.tools._validation import DATA_END, DATA_START, parse_date


async def income_summary(
    user_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> IncomeSummary:
    """Summarize all credits (salary, interest, refunds) for a user over a date range.

    Args:
        user_id: The user whose income to summarize.
        start_date: ISO date YYYY-MM-DD; defaults to the start of available data.
        end_date: ISO date YYYY-MM-DD, inclusive; defaults to the end of available data.
    """
    start = parse_date(start_date, "start_date", DATA_START)
    end = parse_date(end_date, "end_date", DATA_END)

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT txn_date, bank_description, amount FROM transactions
               WHERE user_id = $1 AND txn_type = 'credit'
                 AND txn_date >= $2 AND txn_date <= $3
               ORDER BY txn_date""",
            user_id, start, end,
        )
        monthly = await conn.fetch(
            """SELECT to_char(date_trunc('month', txn_date), 'YYYY-MM') AS month,
                      sum(amount) AS total
               FROM transactions
               WHERE user_id = $1 AND txn_type = 'credit'
                 AND txn_date >= $2 AND txn_date <= $3
               GROUP BY 1 ORDER BY 1""",
            user_id, start, end,
        )

    credits = [
        TransactionRow(txn_date=r["txn_date"], description=r["bank_description"],
                       amount=r["amount"], txn_type="credit")
        for r in rows
    ]
    return IncomeSummary(
        start_date=start, end_date=end,
        total=sum((c.amount for c in credits), start=0),
        txn_count=len(credits),
        by_month=[MonthTotal(month=r["month"], total=r["total"]) for r in monthly],
        credits=credits,
    )
