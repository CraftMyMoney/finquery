"""Typed results the SQL tools return to the agent.

Every number in these models came out of a SQL aggregate or a table row;
the LLM only narrates them. Decimal fields serialize as exact strings, so
nothing is rounded on the way into model context.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class TransactionRow(BaseModel):
    txn_date: date
    description: str
    amount: Decimal
    txn_type: Literal["credit", "debit"]
    category: str | None = None
    subcategory: str | None = None
    spend_type: str | None = None


class BreakdownRow(BaseModel):
    name: str
    total: Decimal
    txn_count: int


class MonthTotal(BaseModel):
    month: str
    total: Decimal


class SpendingSummary(BaseModel):
    start_date: date
    end_date: date
    filters: dict[str, str]
    total: Decimal
    txn_count: int
    grouped_by: str
    breakdown: list[BreakdownRow]
    # populated only when group_by_month is requested; monthly_average is
    # SQL-computed over the calendar months the date range spans
    by_month: list[MonthTotal] = []
    monthly_average: Decimal | None = None


class BudgetLine(BaseModel):
    level: Literal["category", "subcategory"]
    category: str
    subcategory: str | None = None
    budget: Decimal
    actual: Decimal
    variance: Decimal  # actual - budget; positive means over budget
    over_budget: bool


class BudgetReport(BaseModel):
    month: str
    lines: list[BudgetLine]


class MerchantSpend(BaseModel):
    merchant: str
    total: Decimal
    txn_count: int


class TopMerchantsResult(BaseModel):
    start_date: date
    end_date: date
    merchants: list[MerchantSpend]


class IncomeSummary(BaseModel):
    start_date: date
    end_date: date
    total: Decimal
    txn_count: int
    by_month: list[MonthTotal]
    credits: list[TransactionRow]


class SearchResult(BaseModel):
    total_matches: int
    returned: int
    transactions: list[TransactionRow]


class KBChunkHit(BaseModel):
    chunk_id: int
    document_title: str
    publisher: str
    page_ref: str | None = None
    content: str


class KBSearchResult(BaseModel):
    query: str
    retrieval_mode: str  # sparse until embeddings exist; then dense / hybrid_rrf
    hits: list[KBChunkHit]
