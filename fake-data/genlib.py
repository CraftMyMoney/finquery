"""Shared helpers for persona transaction generators.

Each persona script defines three functions taking (gen, month):
  fixed_monthly  -> recurring rows every month
  one_offs       -> month-specific rows
  variable_pool  -> [(weight, factory)] for everyday spends
and calls run() with its own seeded Gen. Deterministic per seed.

Enum values for category/subcategory/spend_type come ONLY from
fake-data/category-list.md. Credits carry blank category columns by decision
(no Income category exists in the taxonomy; income is identified by type).
"""

import csv
import random
from calendar import monthrange
from collections import Counter
from datetime import date

# Derived from fake-data/category-list.md; (category, subcategory) -> spend types.
# Empty tuple = subcategory defines no spend types (spend_type left blank).
ENUMS = {
    ("Essentials", "Bills"): ("Rent", "Electricity", "Water", "Gas", "Phone", "Internet"),
    ("Essentials", "Groceries"): ("Staples", "Vegetables", "Fruits", "Meat", "Eggs"),
    ("Essentials", "Transport"): ("Uber", "Rapido", "Auto", "Cab", "Train", "Fuel"),
    ("Essentials", "Medical"): ("Medicines", "Hospital", "Clinic", "Dentist", "Lab Test"),
    ("Essentials", "EMI"): ("House", "Vehicle", "Education", "Electronics", "Personal"),
    ("Essentials", "Insurance"): ("Health", "Vehicle", "Life", "Electronics", "Others"),
    ("Essentials", "Tax"): ("Income Tax", "GST", "Property Tax", "Others"),
    ("Essentials", "Children"): ("Nutrition", "Necessities", "Toys", "Medical", "Care"),
    ("Essentials", "Services"): ("Laundry", "Tailor", "Courier", "Carpenter", "Plumber"),
    ("Essentials", "Credit Bill"): ("Credit Card", "Simpl", "Slice", "LazyPay", "Amazon Pay"),
    ("Essentials", "Support"): ("Parents", "Spouse", "Mom", "Dad", "Pocket Money"),
    ("Essentials", "Top-up"): ("UPI Lite", "Paytm", "Amazon", "PhonePe", "Others"),
    ("Lifestyle", "Food & Drinks"): ("Eating Out", "Take Away", "Tea & Coffee", "Fast Food", "Snacks"),
    ("Lifestyle", "Shopping"): ("Clothes", "Footwear", "Electronics", "Festival", "Video Games"),
    ("Lifestyle", "Home"): ("Essentials", "Toiletries", "Decor", "Cleaning", "Upkeep"),
    ("Lifestyle", "Entertainment"): ("Movies", "Shows", "Bowling", "Tickets", "Others"),
    ("Lifestyle", "Events"): ("Party", "Spiritual", "Wedding", "Others"),
    ("Lifestyle", "Travel"): ("Activities", "Camping", "Hotel", "Commute", "Meals"),
    ("Lifestyle", "Personal"): ("Self-care", "Grooming", "Hobbies", "Vices", "Therapy"),
    ("Lifestyle", "Fitness"): ("Gym", "Badminton", "Football", "Cricket", "Classes"),
    ("Lifestyle", "Pet Care"): ("Food", "Toys", "Grooming", "Vet", "Others"),
    ("Lifestyle", "Subscription"): ("Netflix", "Prime", "Software", "News", "Others"),
    ("Lifestyle", "Donation"): ("Donation",),
    ("Lifestyle", "Misc"): ("Tip", "Verification", "Forex", "Deposit", "Gift Card"),
    ("Goals", "Investment"): ("Mutual Funds", "Stocks", "IPO", "PPF", "NPS", "Emergency Fund",
                              "Retirement", "House Down Payment", "Car Purchase", "Education Fund",
                              "Wedding Fund", "Vacation Fund"),
    ("Goals", "Business"): ("Salary", "Inventory", "Rent", "Logistics", "Software"),
    ("Goals", "Savings"): (),
    ("Goals", "Gift"): (),
    ("Goals", "Lent"): (),
    ("Goals", "Hidden Charges"): (),
    ("Goals", "Cash Withdrawal"): (),
    ("Goals", "Return"): (),
    ("Goals", "Self Transfer"): (),
}

MONTH_NAMES = {1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
               7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"}

FIELDS = ["date", "bank_description", "amount", "type", "category", "subcategory", "spend_type"]


class Gen:
    """Seeded random helpers; one instance per persona keeps output deterministic."""

    def __init__(self, seed, year=2026):
        self.rng = random.Random(seed)
        self.year = year

    def ref12(self):
        return "".join(self.rng.choice("0123456789") for _ in range(12))

    def upi(self, name, vpa, note):
        return f"UPI-{self.ref12()}-{name}-{vpa}-{note}"

    def txn(self, day, month, desc, amount, ttype, cat="", sub="", spend=""):
        return {
            "date": date(self.year, month, day).isoformat(),
            "bank_description": desc,
            "amount": f"{amount:.2f}",
            "type": ttype,
            "category": cat,
            "subcategory": sub,
            "spend_type": spend,
        }

    def jday(self, month, lo, hi):
        return self.rng.randint(lo, min(hi, monthrange(self.year, month)[1]))

    def amt(self, lo, hi, step=1):
        return self.rng.randrange(int(lo), int(hi) + 1, step)


def validate(rows):
    for r in rows:
        if r["type"] == "credit":
            assert r["category"] == r["subcategory"] == r["spend_type"] == "", r
            continue
        key = (r["category"], r["subcategory"])
        assert key in ENUMS, f"bad category/subcategory: {r}"
        allowed = ENUMS[key]
        if allowed:
            assert r["spend_type"] in allowed, f"bad spend_type: {r}"
        else:
            assert r["spend_type"] == "", f"spend_type must be blank: {r}"


def run(gen, months, target, fixed_monthly, one_offs, variable_pool, out_path):
    all_rows = []
    for m in months:
        rows = fixed_monthly(gen, m) + one_offs(gen, m)
        pool = variable_pool(gen, m)
        weights = [w for w, _ in pool]
        factories = [f for _, f in pool]
        while len(rows) < target:
            rows.append(gen.rng.choices(factories, weights=weights, k=1)[0]())
        rows.sort(key=lambda r: r["date"])
        all_rows.extend(rows)

    validate(all_rows)
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    per_month = Counter(r["date"][:7] for r in all_rows)
    debits = sum(float(r["amount"]) for r in all_rows if r["type"] == "debit")
    credits = sum(float(r["amount"]) for r in all_rows if r["type"] == "credit")
    print(f"wrote {len(all_rows)} rows -> {out_path.name}")
    print("rows/month:", dict(sorted(per_month.items())))
    print(f"total credits: {credits:,.0f}  total debits: {debits:,.0f}")
    for mm in months:
        mc = sum(float(r["amount"]) for r in all_rows
                 if r["type"] == "credit" and r["date"][5:7] == f"{mm:02d}")
        md = sum(float(r["amount"]) for r in all_rows
                 if r["type"] == "debit" and r["date"][5:7] == f"{mm:02d}")
        print(f"  {gen.year}-{mm:02d} credits: {mc:>9,.0f}  debits: {md:>9,.0f}")
