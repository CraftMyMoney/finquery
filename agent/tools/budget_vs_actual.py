"""budget_vs_actual — the seeded budgets table joined against reality.

Budgets exist at category level and (for most) subcategory level; both are
reported so "did I stay within my Lifestyle budget" and "am I over on
Groceries" are the same tool call. Variance is actual minus budget: positive
means over.
"""

from decimal import Decimal

from app.db import get_pool
from agent.schemas import BudgetLine, BudgetReport
from agent.tools._validation import parse_month, resolve_taxonomy


async def budget_vs_actual(user_id: int, month: str, category: str | None = None) -> BudgetReport:
    """Compare budgeted amounts against actual debit spending for one month.

    Args:
        user_id: The user whose budgets to check.
        month: Month to compare, format YYYY-MM, e.g. '2026-05'.
        category: Optional category name to narrow the report (Essentials, Lifestyle, Goals).
    """
    start, end = parse_month(month)

    pool = await get_pool()
    async with pool.acquire() as conn:
        cat_id, _, _ = await resolve_taxonomy(conn, category=category)

        cat_filter = "" if cat_id is None else "AND b.category_id = $4"
        params: list = [user_id, start, end] + ([cat_id] if cat_id is not None else [])

        cat_rows = await conn.fetch(
            f"""SELECT c.name AS category, b.monthly_budget, coalesce(a.total, 0) AS actual
                FROM budgets b
                JOIN categories c ON c.id = b.category_id
                LEFT JOIN (SELECT category_id, sum(amount) AS total FROM transactions
                           WHERE user_id = $1 AND txn_type = 'debit'
                             AND txn_date >= $2 AND txn_date < $3
                           GROUP BY category_id) a ON a.category_id = b.category_id
                WHERE b.user_id = $1 AND b.subcategory_id IS NULL {cat_filter}
                ORDER BY c.name""",
            *params,
        )
        sub_rows = await conn.fetch(
            f"""SELECT c.name AS category, s.name AS subcategory, b.monthly_budget,
                       coalesce(a.total, 0) AS actual
                FROM budgets b
                JOIN categories c ON c.id = b.category_id
                JOIN subcategories s ON s.id = b.subcategory_id
                LEFT JOIN (SELECT subcategory_id, sum(amount) AS total FROM transactions
                           WHERE user_id = $1 AND txn_type = 'debit'
                             AND txn_date >= $2 AND txn_date < $3
                           GROUP BY subcategory_id) a ON a.subcategory_id = b.subcategory_id
                WHERE b.user_id = $1 AND b.subcategory_id IS NOT NULL {cat_filter}
                ORDER BY c.name, s.name""",
            *params,
        )

    def line(r, level: str) -> BudgetLine:
        variance = Decimal(r["actual"]) - Decimal(r["monthly_budget"])
        return BudgetLine(
            level=level, category=r["category"],
            subcategory=r["subcategory"] if level == "subcategory" else None,
            budget=r["monthly_budget"], actual=r["actual"],
            variance=variance, over_budget=variance > 0,
        )

    lines = [line(r, "category") for r in cat_rows] + [line(r, "subcategory") for r in sub_rows]
    return BudgetReport(month=month, lines=lines)
