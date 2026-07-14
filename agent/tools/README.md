# Agent tools

Six typed tools, one file each, following the cohort single-agent-lab
conventions: plain async functions with Google-style Args docstrings (Pydantic
AI derives the tool schema from them), typed Pydantic results
(`agent/schemas.py`), and ModelRetry for self-correctable mistakes (unknown
taxonomy names reply with the valid options; bad dates reply with the format).

| File | Tool | Purpose |
|---|---|---|
| `spending_by_category.py` | spending_by_category | Sum/aggregate spend by category/subcategory over a date range |
| `budget_vs_actual.py` | budget_vs_actual | Compare actual spend against the seeded budgets table |
| `top_merchants.py` | top_merchants | Rank counterparties by spend (pseudonymized names) |
| `income_summary.py` | income_summary | Credits summary over a period (salary, interest, refunds) |
| `search_transactions.py` | search_transactions | Filtered transaction lookup (date, amount, category, text) |
| `search_finance_kb.py` | search_finance_kb | Hybrid dense+BM25 search over KB chunks, merged with RRF |

The five SQL tools are implemented and tested against the live seeded DB;
tests cross-check their outputs against `eval/ground_truth.json`, so the tools
provably reproduce the eval's expected answers. `search_finance_kb` lands in
the key-dependent phase. Tool outputs pass through the PII gate (`pii/`) at
the agent boundary, not inside the tools; `user_id` is bound from request
context at agent wiring time, never chosen by the model.
