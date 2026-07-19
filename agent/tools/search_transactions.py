"""search_transactions — the lookup tool.

Everything the other tools aggregate, this one lists: filtered rows for
"when did I pay X" and "show me my largest expense" questions. total_matches
is reported alongside the capped page so the agent knows when it is looking
at a truncated view and can narrow the filters instead of guessing.
"""

from pydantic_ai import ModelRetry

from app.db import get_pool
from agent.schemas import SearchResult, TransactionRow
from agent.tools._validation import DATA_END, DATA_START, parse_date, resolve_taxonomy

_ORDERINGS = {
    "date": "t.txn_date DESC, t.id DESC",
    "amount": "t.amount DESC, t.txn_date DESC",
}


async def search_transactions(
    user_id: int,
    text: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    txn_type: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    order_by: str = "date",
    limit: int = 20,
) -> SearchResult:
    """Search individual transactions with filters; returns matching rows.

    Args:
        user_id: The user whose transactions to search.
        text: Optional case-insensitive words matched against the bank narration;
            every word must appear, in any order (e.g. 'books uniform' matches
            'ANNUAL BOOKS AND UNIFORM FEE').
        category: Optional category name (Essentials, Lifestyle, Goals).
        subcategory: Optional subcategory name, e.g. 'Groceries', 'EMI'.
        txn_type: Optional 'credit' or 'debit'.
        min_amount: Optional lower bound on amount.
        max_amount: Optional upper bound on amount.
        start_date: ISO date YYYY-MM-DD; defaults to the start of available data.
        end_date: ISO date YYYY-MM-DD, inclusive; defaults to the end of available data.
        order_by: 'date' (newest first, default) or 'amount' (largest first).
        limit: Max rows to return (1-50, default 20).
    """
    start = parse_date(start_date, "start_date", DATA_START)
    end = parse_date(end_date, "end_date", DATA_END)
    if order_by not in _ORDERINGS:
        raise ModelRetry(f"order_by={order_by!r} is not valid; use 'date' or 'amount'.")
    if txn_type is not None and txn_type not in ("credit", "debit"):
        raise ModelRetry(f"txn_type={txn_type!r} is not valid; use 'credit' or 'debit'.")
    limit = max(1, min(limit, 50))

    pool = await get_pool()
    async with pool.acquire() as conn:
        cat_id, sub_id, _ = await resolve_taxonomy(conn, category, subcategory)

        where = ["t.user_id = $1", "t.txn_date >= $2", "t.txn_date <= $3"]
        params: list = [user_id, start, end]

        def add(clause: str, value) -> None:
            params.append(value)
            where.append(clause.format(n=len(params)))

        if text is not None:
            # one ILIKE per word: the model passes word bags like "school books
            # uniform fee" and no narration carries them as one substring
            for word in text.split():
                add("t.bank_description ILIKE ${n}", f"%{word}%")
        if cat_id is not None:
            add("t.category_id = ${n}", cat_id)
        if sub_id is not None:
            add("t.subcategory_id = ${n}", sub_id)
        if txn_type is not None:
            add("t.txn_type = ${n}", txn_type)
        if min_amount is not None:
            add("t.amount >= ${n}", min_amount)
        if max_amount is not None:
            add("t.amount <= ${n}", max_amount)

        rows = await conn.fetch(
            f"""SELECT t.txn_date, t.bank_description, t.amount, t.txn_type,
                       c.name AS category, s.name AS subcategory, st.name AS spend_type,
                       count(*) OVER () AS total_matches
                FROM transactions t
                LEFT JOIN categories c ON c.id = t.category_id
                LEFT JOIN subcategories s ON s.id = t.subcategory_id
                LEFT JOIN spend_types st ON st.id = t.spend_type_id
                WHERE {' AND '.join(where)}
                ORDER BY {_ORDERINGS[order_by]}
                LIMIT {limit}""",
            *params,
        )

    transactions = [
        TransactionRow(
            txn_date=r["txn_date"], description=r["bank_description"], amount=r["amount"],
            txn_type=r["txn_type"], category=r["category"], subcategory=r["subcategory"],
            spend_type=r["spend_type"],
        )
        for r in rows
    ]
    return SearchResult(
        total_matches=rows[0]["total_matches"] if rows else 0,
        returned=len(transactions),
        transactions=transactions,
    )
