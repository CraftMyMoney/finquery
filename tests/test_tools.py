"""SQL tool tests against the live seeded DB, cross-checked against the
committed eval ground truth: a tool that cannot reproduce ground_truth.json
would fail the eval anyway, so it fails here first.

Requires the dockerized Postgres (docker compose up -d db + seed scripts);
skips cleanly if it is not reachable.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic_ai import ModelRetry

from app.db import close_pool, ping
from agent.tools import (
    budget_vs_actual,
    income_summary,
    search_transactions,
    spending_by_category,
    top_merchants,
)
from agent.tools.top_merchants import merchant_from_narration

GT = json.loads(
    (Path(__file__).resolve().parent.parent / "eval" / "ground_truth.json").read_text()
)


@pytest.fixture(autouse=True)
async def _db():
    # each test runs in its own event loop; drop any pool a previous loop cached
    await close_pool()
    if not await ping():
        await close_pool()
        pytest.skip("seeded DB not reachable on DATABASE_URL")
    yield
    await close_pool()


# ---------------------------------------------------------------- spending_by_category

async def test_groceries_june_matches_ground_truth():
    result = await spending_by_category(
        1, subcategory="Groceries", start_date="2026-06-01", end_date="2026-06-30"
    )
    assert result.total == Decimal(GT["agg-01"]["value"])
    assert result.grouped_by == "spend_type"
    assert sum(b.total for b in result.breakdown) == result.total


async def test_unfiltered_may_total_matches_ground_truth():
    result = await spending_by_category(1, start_date="2026-05-01", end_date="2026-05-31")
    assert result.total == Decimal(GT["agg-02"]["value"])
    assert result.grouped_by == "category"
    assert {b.name for b in result.breakdown} <= {"Essentials", "Lifestyle", "Goals"}


async def test_emi_march_and_mutual_funds_total():
    emi = await spending_by_category(
        1, subcategory="EMI", start_date="2026-03-01", end_date="2026-03-31"
    )
    assert emi.total == Decimal(GT["agg-04"]["value"])

    mf = await spending_by_category(1, spend_type="Mutual Funds")
    assert mf.total == Decimal(GT["agg-06"]["value"])
    assert mf.grouped_by == "none"


async def test_category_name_is_case_insensitive():
    result = await spending_by_category(1, subcategory="groceries")
    assert result.txn_count == 95


async def test_unknown_category_raises_model_retry_with_options():
    with pytest.raises(ModelRetry, match="Essentials"):
        await spending_by_category(1, category="Essential")


async def test_ambiguous_spend_type_asks_for_subcategory():
    # 'Vehicle' exists under both EMI and Insurance
    with pytest.raises(ModelRetry, match="multiple subcategories"):
        await spending_by_category(1, spend_type="Vehicle")
    ok = await spending_by_category(1, subcategory="Insurance", spend_type="Vehicle")
    assert ok.total == Decimal("8200.00")


# ---------------------------------------------------------------- budget_vs_actual

async def test_may_travel_blowout_matches_ground_truth():
    report = await budget_vs_actual(1, "2026-05")
    travel = next(l for l in report.lines if l.subcategory == "Travel")
    assert travel.actual == Decimal(GT["comp-02"]["components"]["may_travel_actual"])
    assert travel.budget == Decimal("1500.00")
    assert travel.over_budget and travel.variance == Decimal("13650.00")

    lifestyle = next(l for l in report.lines if l.level == "category" and l.category == "Lifestyle")
    assert lifestyle.actual == Decimal(GT["comp-02"]["components"]["may_lifestyle_actual"])
    assert lifestyle.budget == Decimal(GT["comp-02"]["components"]["lifestyle_budget"])


async def test_budget_report_category_filter():
    report = await budget_vs_actual(1, "2026-05", category="Lifestyle")
    assert report.lines and all(l.category == "Lifestyle" for l in report.lines)


async def test_bad_month_raises_model_retry():
    with pytest.raises(ModelRetry, match="YYYY-MM"):
        await budget_vs_actual(1, "May 2026")


# ---------------------------------------------------------------- top_merchants

def test_merchant_parsing_covers_every_seed_format():
    cases = {
        "UPI-160733754330-RAMULU VEGETABLES-9701234567@ybl-VEGETABLES": "RAMULU VEGETABLES",
        "POS 416021XXXXXX8907 DMART AVENUE KUKATPALLY": "DMART AVENUE KUKATPALLY",
        "ACH D-HDFC LTD HOME LOAN-LN00458912337-EMI": "HDFC LTD HOME LOAN",
        "IMPS-P2A-945116868548-RAJESHWAR RAO-XXXXXX4521-MONTHLY SUPPORT": "RAJESHWAR RAO",
        "NWD-416021XXXXXX8907-ATM CASH-AMEERPET HYD-706324241541": "ATM CASH WITHDRAWAL",
        "IB BILLPAY DR-INCOME TAX-ADVANCE TAX AY2026-27-CIN709682506710": "INCOME TAX",
        "IRCTC CF-111554262218-SC HYD TO VSKP 4 PAX": "IRCTC",
        "NEFT CR-HDFC0000123-TECHNOVA SOFTWARE PVT LTD-SALARY JAN 2026-N104332181960":
            "TECHNOVA SOFTWARE PVT LTD",
        "TRANSFER TO PPF A/C XXXXXX8899": "PPF TRANSFER",
    }
    for narration, merchant in cases.items():
        assert merchant_from_narration(narration) == merchant


async def test_top_merchant_is_the_home_loan():
    result = await top_merchants(1, limit=5)
    first = result.merchants[0]
    assert first.merchant == "HDFC LTD HOME LOAN"
    assert first.total == Decimal("135000.00") and first.txn_count == 6


# ---------------------------------------------------------------- income_summary

async def test_march_income_matches_ground_truth():
    result = await income_summary(1, start_date="2026-03-01", end_date="2026-03-31")
    assert result.total == Decimal(GT["agg-07"]["value"])
    assert result.txn_count == 2  # salary + interest capitalisation
    assert result.by_month == result.by_month and result.by_month[0].month == "2026-03"


async def test_full_period_income_lists_all_credits():
    result = await income_summary(1)
    assert result.txn_count == 9
    assert len(result.by_month) == 6


# ---------------------------------------------------------------- search_transactions

async def test_text_search_finds_the_zomato_refund():
    result = await search_transactions(1, text="ZOMATO REFUND")
    assert result.total_matches == result.returned == 1
    txn = result.transactions[0]
    gt = GT["look-05"]["value"]
    assert txn.txn_date == date.fromisoformat(gt["txn_date"])
    assert txn.amount == Decimal(gt["amount"])


async def test_order_by_amount_surfaces_largest_debit():
    result = await search_transactions(1, txn_type="debit", order_by="amount", limit=1)
    assert result.transactions[0].amount == Decimal(GT["look-02"]["value"]["amount"])
    # full match count is reported honestly alongside the capped page
    assert result.total_matches == 351  # user1: 360 rows - 9 credits


async def test_search_validates_order_by_and_txn_type():
    with pytest.raises(ModelRetry, match="order_by"):
        await search_transactions(1, order_by="biggest")
    with pytest.raises(ModelRetry, match="txn_type"):
        await search_transactions(1, txn_type="expense")
