"""The agent's tools, one file each (mentor-lab convention). Five SQL tools
plus search_finance_kb (sparse-only until embeddings exist)."""

from agent.tools.budget_vs_actual import budget_vs_actual
from agent.tools.income_summary import income_summary
from agent.tools.search_finance_kb import search_finance_kb
from agent.tools.search_transactions import search_transactions
from agent.tools.spending_by_category import spending_by_category
from agent.tools.top_merchants import top_merchants

SQL_TOOLS = [
    spending_by_category,
    budget_vs_actual,
    top_merchants,
    income_summary,
    search_transactions,
]

__all__ = ["SQL_TOOLS", "budget_vs_actual", "income_summary", "search_finance_kb",
           "search_transactions", "spending_by_category", "top_merchants"]
