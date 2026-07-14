"""top_merchants — rank counterparties by debit spend.

Merchant names are not a column; they are parsed deterministically from the
bank narration formats present in the seed data (UPI, POS, ACH, IMPS, NWD,
IB BILLPAY, IRCTC). Parsing lives here in Python so it is unit-testable;
grouping/summing still happens on parsed exact Decimals, never in the LLM.
Names that are PII are caught by the pseudonymization gate at the LLM
boundary, not here.
"""

from collections import defaultdict
from decimal import Decimal

from app.db import get_pool
from agent.schemas import MerchantSpend, TopMerchantsResult
from agent.tools._validation import DATA_END, DATA_START, parse_date


def merchant_from_narration(description: str) -> str:
    """Extract the counterparty from a bank narration, format by format."""
    d = description
    if d.startswith("UPI-"):          # UPI-<ref>-<MERCHANT>-<vpa>-<note>
        return d.split("-")[2]
    if d.startswith("POS "):          # POS <card> <MERCHANT...>
        return d.split(" ", 2)[2]
    if d.startswith("ACH D-"):        # ACH D-<MERCHANT>-<ref>-<note>
        return d.split("-")[1]
    if d.startswith("IMPS-"):         # IMPS-P2A-<ref>-<NAME>-<acct>-<note>
        parts = d.split("-")
        return parts[3] if len(parts) > 3 else d
    if d.startswith("NWD-"):          # ATM withdrawal
        return "ATM CASH WITHDRAWAL"
    if d.startswith("IB BILLPAY DR-"):
        return d.split("-")[1]
    if d.startswith("IRCTC"):
        return "IRCTC"
    if d.startswith("NEFT CR-"):      # NEFT CR-<ifsc>-<SENDER>-<note>-<ref>
        parts = d.split("-")
        return parts[2] if len(parts) > 2 else d
    if d.startswith("TRANSFER TO PPF"):
        return "PPF TRANSFER"
    return d[:40]


async def top_merchants(
    user_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 5,
) -> TopMerchantsResult:
    """Rank merchants/counterparties by total debit spend over a date range.

    Args:
        user_id: The user whose spending to rank.
        start_date: ISO date YYYY-MM-DD; defaults to the start of available data.
        end_date: ISO date YYYY-MM-DD, inclusive; defaults to the end of available data.
        limit: How many merchants to return (1-25, default 5).
    """
    start = parse_date(start_date, "start_date", DATA_START)
    end = parse_date(end_date, "end_date", DATA_END)
    limit = max(1, min(limit, 25))

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT bank_description, amount FROM transactions
               WHERE user_id = $1 AND txn_type = 'debit'
                 AND txn_date >= $2 AND txn_date <= $3""",
            user_id, start, end,
        )

    totals: dict[str, Decimal] = defaultdict(Decimal)
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        merchant = merchant_from_narration(r["bank_description"])
        totals[merchant] += r["amount"]
        counts[merchant] += 1

    ranked = sorted(totals, key=lambda m: totals[m], reverse=True)[:limit]
    return TopMerchantsResult(
        start_date=start, end_date=end,
        merchants=[MerchantSpend(merchant=m, total=totals[m], txn_count=counts[m]) for m in ranked],
    )
