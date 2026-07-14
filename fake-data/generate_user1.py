"""Generate synthetic 6-month transaction CSV for user1 (familyMan persona).

Salaried employee, Rs 1,00,000/month, family with 2 kids, house + vehicle EMIs.
Jan 1 to Jun 30, 2026, ~60 transactions/month. Deterministic (seed 42).

Descriptions intentionally carry realistic FAKE PII (VPAs, phone numbers,
masked account/card refs) so the pseudonymization layer has real work to do.

Usage: python3 fake-data/generate_user1.py
"""

from pathlib import Path

from genlib import MONTH_NAMES, Gen, run

SEED = 42
MONTHS = [1, 2, 3, 4, 5, 6]
TARGET_PER_MONTH = 60
OUT = Path(__file__).parent / "user1_familyman_transactions.csv"


# ---------------------------------------------------------------- fixed monthly
def fixed_monthly(g, m):
    rows = [
        g.txn(1, m, f"NEFT CR-HDFC0000123-TECHNOVA SOFTWARE PVT LTD-SALARY {MONTH_NAMES[m]} {g.year}-N{g.ref12()}",
              100000, "credit"),
        g.txn(5, m, "ACH D-HDFC LTD HOME LOAN-LN00458912337-EMI",
              22500, "debit", "Essentials", "EMI", "House"),
        g.txn(7, m, "ACH D-ICICI BANK VEHICLE LOAN-LVHYD00812345-EMI",
              6150, "debit", "Essentials", "EMI", "Vehicle"),
        g.txn(3, m, "ACH D-INDIAN CLEARING CORP-AXIS BLUECHIP FUND SIP-IN{ref}".format(ref=g.ref12()),
              8000, "debit", "Goals", "Investment", "Mutual Funds"),
        g.txn(3, m, "TRANSFER TO PPF A/C XXXXXX8899-SELF",
              2500, "debit", "Goals", "Investment", "PPF"),
        g.txn(4, m, "ACH D-INDIAN CLEARING CORP-HDFC CHILDRENS GIFT FUND SIP-IN{ref}".format(ref=g.ref12()),
              2000, "debit", "Goals", "Investment", "Education Fund"),
        g.txn(g.jday(m, 2, 4), m, g.upi("LITTLE FLOWER HIGH SCHOOL", "littleflower.fees@okaxis", f"TUITION FEE {MONTH_NAMES[m]}"),
              4200, "debit", "Essentials", "Children", "Care"),
        g.txn(g.jday(m, 5, 8), m, g.upi("SUNITHA TUITIONS", "sunitha.classes@okhdfcbank", "MONTHLY TUITION"),
              1500, "debit", "Essentials", "Children", "Care"),
        g.txn(g.jday(m, 8, 12), m, f"IMPS-P2A-{g.ref12()}-RAJESHWAR RAO-XXXXXX4521-MONTHLY SUPPORT",
              5000, "debit", "Essentials", "Support", "Parents"),
        g.txn(g.jday(m, 12, 16), m, g.upi("CRED CLUB", "cred.club@axisb", "HDFC CC XXXXXX8907 BILL PAYMENT"),
              g.amt(5500, 9500, 100), "debit", "Essentials", "Credit Bill", "Credit Card"),
        g.txn(g.jday(m, 6, 9), m, g.upi("TSSPDCL", "billpay.tsspdcl@icici", "USN 214365879012"),
              # electricity ramps up in summer (Apr-Jun): seasonal trend for evals
              g.amt(1100, 1500) if m <= 3 else g.amt(2200, 3100), "debit", "Essentials", "Bills", "Electricity"),
        g.txn(g.jday(m, 9, 12), m, f"UPI-{g.ref12()}-AIRTEL POSTPAID-9848012345@airtel-BILL 9848012345",
              599, "debit", "Essentials", "Bills", "Phone"),
        g.txn(g.jday(m, 10, 14), m, g.upi("ACT FIBERNET", "actcorp@icici", "ACCT 10098765"),
              999, "debit", "Essentials", "Bills", "Internet"),
        g.txn(g.jday(m, 14, 18), m, g.upi("HMWSSB", "hmwssb.billdesk@hdfcbank", "CAN 22334455"),
              g.amt(280, 420, 10), "debit", "Essentials", "Bills", "Water"),
        g.txn(g.jday(m, 15, 18), m, "POS 416021XXXXXX8907 NETFLIX COM MUMBAI",
              649, "debit", "Lifestyle", "Subscription", "Netflix"),
        g.txn(g.jday(m, 20, 24), m, f"NWD-416021XXXXXX8907-ATM CASH-AMEERPET HYD-{g.ref12()}",
              g.amt(2000, 3000, 500), "debit", "Goals", "Cash Withdrawal", ""),
        g.txn(g.jday(m, 24, 27), m, g.upi("SUGUNA MAID SERVICES", "9912345670@ybl", "MAID AND COOK SALARY"),
              3500, "debit", "Essentials", "Services", "Laundry"),
    ]
    if m in (1, 3, 5):  # gas cylinder roughly every other month
        rows.append(g.txn(g.jday(m, 11, 20), m, g.upi("HP GAS RAMDEV AGENCY", "hpgas.ramdev@okicici", "CYL BOOKING 9848012345"),
                          g.amt(880, 950, 5), "debit", "Essentials", "Bills", "Gas"))
    return rows


# ---------------------------------------------------------------- one-offs
def one_offs(g, m):
    rows = []
    if m == 1:  # Sankranti festival shopping + health insurance quarterly
        rows += [
            g.txn(12, 1, "POS 416021XXXXXX8907 TRENDS APPAREL HYDERABAD",
                  4850, "debit", "Lifestyle", "Shopping", "Festival"),
            g.txn(13, 1, g.upi("CHANDANA BROTHERS", "chandanabros@okhdfcbank", "SANKRANTI KIDS WEAR"),
                  3200, "debit", "Lifestyle", "Shopping", "Clothes"),
            g.txn(9, 1, "ACH D-STAR HEALTH INSURANCE-POL SH2026114455-QTRLY PREMIUM",
                  4500, "debit", "Essentials", "Insurance", "Health"),
            g.txn(15, 1, g.upi("SRI VENKATESWARA TEMPLE", "svtemple.hyd@oksbi", "SANKRANTI DONATION"),
                  1116, "debit", "Lifestyle", "Donation", "Donation"),
        ]
    if m == 2:  # vehicle insurance annual + dentist + Prime annual
        rows += [
            g.txn(10, 2, "ACH D-BAJAJ ALLIANZ GIC-POL VEH2026778899-CAR OD PREMIUM",
                  8200, "debit", "Essentials", "Insurance", "Vehicle"),
            g.txn(18, 2, g.upi("SMILE DENTAL CLINIC", "smiledental@okaxis", "ROOT CANAL SITTING 1"),
                  3500, "debit", "Essentials", "Medical", "Dentist"),
            g.txn(6, 2, "POS 416021XXXXXX8907 AMAZON PRIME MEMBERSHIP",
                  1499, "debit", "Lifestyle", "Subscription", "Prime"),
        ]
    if m == 3:  # LIC quarterly + advance tax + FY-end interest credit + school annual fee part
        rows += [
            g.txn(12, 3, g.upi("LIC OF INDIA", "licindia.premium@sbi", "POL 667788990 QTRLY"),
                  6100, "debit", "Essentials", "Insurance", "Life"),
            g.txn(14, 3, "IB BILLPAY DR-INCOME TAX-SELF ASSESSMENT AY2026-27-CIN{ref}".format(ref=g.ref12()),
                  4800, "debit", "Essentials", "Tax", "Income Tax"),
            g.txn(31, 3, "CREDIT INTEREST CAPITALISED-SB A/C XXXXXX2210",
                  812, "credit"),
            g.txn(20, 3, g.upi("LITTLE FLOWER HIGH SCHOOL", "littleflower.fees@okaxis", "ANNUAL BOOKS AND UNIFORM"),
                  7800, "debit", "Essentials", "Children", "Necessities"),
        ]
    if m == 4:  # health insurance quarterly + summer camp + AC service
        rows += [
            g.txn(9, 4, "ACH D-STAR HEALTH INSURANCE-POL SH2026114455-QTRLY PREMIUM",
                  4500, "debit", "Essentials", "Insurance", "Health"),
            g.txn(20, 4, g.upi("KIDZEE SUMMER CAMP", "kidzee.hyd@okicici", "SUMMER CAMP 2 KIDS"),
                  3000, "debit", "Essentials", "Children", "Care"),
            g.txn(16, 4, g.upi("COOLTECH AC SERVICES", "9700112233@paytm", "AC SERVICE 2 UNITS"),
                  1400, "debit", "Lifestyle", "Home", "Upkeep"),
        ]
    if m == 5:  # family vacation (over-budget month) + wedding gift
        rows += [
            g.txn(8, 5, "IRCTC CF-{ref}-SC HYD TO VSKP 4 PAX".format(ref=g.ref12()),
                  2460, "debit", "Essentials", "Transport", "Train"),
            g.txn(9, 5, g.upi("SEA PEARL BEACH RESORT", "seapearl.vizag@okhdfcbank", "3N FAMILY STAY"),
                  9800, "debit", "Lifestyle", "Travel", "Hotel"),
            g.txn(10, 5, g.upi("VIZAG SCUBA ADVENTURES", "vizagscuba@ybl", "BOAT RIDE FAMILY"),
                  2200, "debit", "Lifestyle", "Travel", "Activities"),
            g.txn(10, 5, g.upi("SAI RAM PARLOUR VSKP", "9866554433@ybl", "FAMILY LUNCH"),
                  1350, "debit", "Lifestyle", "Travel", "Meals"),
            g.txn(11, 5, g.upi("KURSURA CABS VIZAG", "kursura.cabs@paytm", "LOCAL SIGHTSEEING CAB"),
                  1800, "debit", "Lifestyle", "Travel", "Commute"),
            g.txn(12, 5, "IRCTC CF-{ref}-SC VSKP TO HYD 4 PAX".format(ref=g.ref12()),
                  2460, "debit", "Essentials", "Transport", "Train"),
            g.txn(24, 5, f"IMPS-P2A-{g.ref12()}-SRINIVAS KUMAR-XXXXXX7788-MARRIAGE GIFT",
                  5001, "debit", "Lifestyle", "Events", "Wedding"),
        ]
    if m == 6:  # LIC quarterly + school reopening + interest + Zomato refund
        rows += [
            g.txn(12, 6, g.upi("LIC OF INDIA", "licindia.premium@sbi", "POL 667788990 QTRLY"),
                  6100, "debit", "Essentials", "Insurance", "Life"),
            g.txn(8, 6, "POS 416021XXXXXX8907 SCHOLARS STATIONERY HYD",
                  2350, "debit", "Essentials", "Children", "Necessities"),
            g.txn(9, 6, g.upi("BATA SHOE STORE KPHB", "bata.kphb@okaxis", "KIDS SCHOOL SHOES"),
                  1750, "debit", "Essentials", "Children", "Necessities"),
            g.txn(30, 6, "CREDIT INTEREST CAPITALISED-SB A/C XXXXXX2210",
                  798, "credit"),
            g.txn(17, 6, f"UPI-{g.ref12()}-ZOMATO REFUND-zomato.refunds@hdfcbank-ORDER CANCELLED",
                  340, "credit"),
        ]
    return rows


# ---------------------------------------------------------------- variable pool
def variable_pool(g, m):
    """Weighted everyday spends; each entry is (weight, factory)."""
    return [
        (10, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("RAMULU VEGETABLES", "9701234567@ybl", "VEGETABLES"),
                           g.amt(80, 350, 10), "debit", "Essentials", "Groceries", "Vegetables")),
        (4, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("SRI KANAKA FRUITS", "srifruits@paytm", "FRUITS"),
                          g.amt(120, 380, 10), "debit", "Essentials", "Groceries", "Fruits")),
        (3, lambda: g.txn(g.jday(m, 1, 28), m, "POS 416021XXXXXX8907 DMART AVENUE KUKATPALLY",
                          g.amt(1400, 2600, 50), "debit", "Essentials", "Groceries", "Staples")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("BIGBASKET", "bigbasket@hdfcbank", "ORDER BB{r}".format(r=g.ref12()[:8])),
                          g.amt(600, 1400, 50), "debit", "Essentials", "Groceries", "Staples")),
        (3, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("FRESH MEAT HOME", "freshmeat.hyd@okicici", "SUNDAY ORDER"),
                          g.amt(320, 620, 20), "debit", "Essentials", "Groceries", "Meat")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("SS EGG CENTRE", "9885012345@ybl", "EGGS 30PC TRAY"),
                          g.amt(180, 220, 5), "debit", "Essentials", "Groceries", "Eggs")),
        (4, lambda: g.txn(g.jday(m, 1, 28), m, "POS 416021XXXXXX8907 IOCL SRI SAI FUEL STN",
                          g.amt(1300, 1800, 50), "debit", "Essentials", "Transport", "Fuel")),
        (4, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("UBER INDIA", "uber.rides@axisb", "TRIP {r}".format(r=g.ref12()[:8])),
                          g.amt(140, 420, 10), "debit", "Essentials", "Transport", "Uber")),
        (3, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("RAPIDO BIKE TAXI", "rapido@ybl", "RIDE"),
                          g.amt(60, 160, 10), "debit", "Essentials", "Transport", "Rapido")),
        (3, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("AUTO ANNA", "9963321100@paytm", "AUTO FARE"),
                          g.amt(50, 140, 10), "debit", "Essentials", "Transport", "Auto")),
        (3, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("SWIGGY", "swiggy@icici", "ORDER {r}".format(r=g.ref12()[:8])),
                          g.amt(240, 520, 10), "debit", "Lifestyle", "Food & Drinks", "Take Away")),
        (3, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("ZOMATO", "zomato.order@hdfcbank", "ORDER {r}".format(r=g.ref12()[:8])),
                          g.amt(260, 560, 10), "debit", "Lifestyle", "Food & Drinks", "Fast Food")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("PARADISE BIRYANI KPHB", "paradise.kphb@okhdfcbank", "FAMILY DINNER"),
                          g.amt(850, 1500, 50), "debit", "Lifestyle", "Food & Drinks", "Eating Out")),
        (3, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("CHAI POINT", "9848998877@okaxis", "TEA SNACKS"),
                          g.amt(40, 120, 10), "debit", "Lifestyle", "Food & Drinks", "Tea & Coffee")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("SRI SAI BAKERY", "saibakery.kphb@ybl", "SNACKS"),
                          g.amt(80, 220, 10), "debit", "Lifestyle", "Food & Drinks", "Snacks")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("APOLLO PHARMACY", "apollopharmacy@icici", "MEDICINES"),
                          g.amt(180, 520, 10), "debit", "Essentials", "Medical", "Medicines")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("HORLICKS KIRANA MART", "9876501234@ybl", "KIDS HEALTH DRINK DIAPERS"),
                          g.amt(450, 900, 10), "debit", "Essentials", "Children", "Nutrition")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, "POS 416021XXXXXX8907 RATNADEEP SUPER MARKET",
                          g.amt(300, 700, 10), "debit", "Lifestyle", "Home", "Toiletries")),
        (1, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("URBAN COMPANY", "urbancompany@axisb", "HOME CLEANING"),
                          g.amt(600, 900, 50), "debit", "Lifestyle", "Home", "Cleaning")),
        (1, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("NEW STYLE SALOON", "9700998866@paytm", "HAIRCUT"),
                          g.amt(150, 300, 50), "debit", "Lifestyle", "Personal", "Grooming")),
        (1, lambda: g.txn(g.jday(m, 1, 28), m, "POS 416021XXXXXX8907 PVR ICON HYDERABAD",
                          g.amt(800, 1400, 50), "debit", "Lifestyle", "Entertainment", "Movies")),
        (1, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("AMAZON PAY RECHARGE", "amazonpay@apl", "UPI LITE TOPUP"),
                          g.amt(200, 500, 100), "debit", "Essentials", "Top-up", "Amazon")),
    ]


if __name__ == "__main__":
    run(Gen(SEED), MONTHS, TARGET_PER_MONTH, fixed_monthly, one_offs, variable_pool, OUT)
