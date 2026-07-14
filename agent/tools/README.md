# Agent tools

Six typed tools, one file each, per the design doc:

| File (planned) | Tool | Purpose |
|---|---|---|
| `spending_by_category.py` | spending_by_category | Sum/aggregate spend by category/subcategory over a date range |
| `budget_vs_actual.py` | budget_vs_actual | Compare actual spend against the seeded budgets table |
| `top_merchants.py` | top_merchants | Rank counterparties by spend (pseudonymized names) |
| `income_summary.py` | income_summary | Credits summary over a period (salary, interest, refunds) |
| `search_transactions.py` | search_transactions | Filtered transaction lookup (date, amount, category, text) |
| `search_finance_kb.py` | search_finance_kb | Hybrid dense+BM25 search over KB chunks, merged with RRF |

Tool implementations land with the agent (key-dependent phase). SQL tools are
pure functions over asyncpg with typed, validated arguments; taxonomy values
are validated against the enums before hitting SQL.
