"""Generate synthetic 6-month transaction CSV for user2 (gigFreelancer persona).

Freelance designer, IRREGULAR income: 0-3 client invoice credits/month
(April is a zero-income dry month). Rents a flat, coworking seat, part-time
assistant, laptop EMI. Invests only in good-income months (Jan, Mar, Jun).
Exercises the Business spend types user1 never touches. Seed 7.

Usage: python3 fake-data/generate_user2.py
"""

from pathlib import Path

from genlib import Gen, run

SEED = 7
MONTHS = [1, 2, 3, 4, 5, 6]
TARGET_PER_MONTH = 55
OUT = Path(__file__).parent / "user2_gigfreelancer_transactions.csv"

# (day, client, ifsc, amount) per month; April intentionally empty (dry month)
INVOICES = {
    1: [(5, "PIXELWORKS STUDIO", "ICIC0002244", 35000),
        (18, "NEXGEN DIGITAL LLP", "HDFC0001177", 28000),
        (27, "VERTEX MEDIA", "UTIB0003355", 22000)],
    2: [(9, "PIXELWORKS STUDIO", "ICIC0002244", 25000),
        (24, "TULIP EVENTS", "SBIN0004466", 20000)],
    3: [(4, "NEXGEN DIGITAL LLP", "HDFC0001177", 40000),
        (16, "PIXELWORKS STUDIO", "ICIC0002244", 30000),
        (29, "BRANDCRAFT AGENCY", "KKBK0005588", 25000)],
    4: [],
    5: [(12, "VERTEX MEDIA", "UTIB0003355", 32000),
        (26, "PIXELWORKS STUDIO", "ICIC0002244", 28000)],
    6: [(6, "BRANDCRAFT AGENCY", "KKBK0005588", 30000),
        (19, "NEXGEN DIGITAL LLP", "HDFC0001177", 26000),
        (30, "TULIP EVENTS", "SBIN0004466", 22000)],
}


def fixed_monthly(g, m):
    rows = [
        g.txn(day, m, f"NEFT CR-{ifsc}-{client}-INV FQ2026-{g.ref12()[:6]}-N{g.ref12()}",
              amount, "credit")
        for day, client, ifsc, amount in INVOICES[m]
    ]
    rows += [
        g.txn(1, m, f"IMPS-P2A-{g.ref12()}-MRS PADMAVATHI DEVI-XXXXXX9911-FLAT RENT",
              18000, "debit", "Essentials", "Bills", "Rent"),
        g.txn(2, m, g.upi("91SPRINGBOARD HITEC", "91springboard.hyd@icici", "COWORKING SEAT"),
              6000, "debit", "Goals", "Business", "Rent"),
        g.txn(g.jday(m, 1, 3), m, f"IMPS-P2A-{g.ref12()}-KAVYA REDDY-XXXXXX2233-ASSISTANT STIPEND",
              8000, "debit", "Goals", "Business", "Salary"),
        g.txn(6, m, "ACH D-BAJAJ FINSERV-LAPTOP LOAN L2XN887766-EMI",
              4499, "debit", "Essentials", "EMI", "Electronics"),
        g.txn(g.jday(m, 4, 7), m, "POS 453210XXXXXX1122 ADOBE CREATIVE CLOUD",
              1675, "debit", "Lifestyle", "Subscription", "Software"),
        g.txn(g.jday(m, 4, 7), m, "POS 453210XXXXXX1122 FIGMA PROFESSIONAL",
              1299, "debit", "Lifestyle", "Subscription", "Software"),
        g.txn(g.jday(m, 8, 11), m, f"UPI-{g.ref12()}-JIO PREPAID-9012345678@jio-RECHARGE 9012345678",
              479, "debit", "Essentials", "Bills", "Phone"),
        g.txn(g.jday(m, 9, 13), m, g.upi("AIRTEL XSTREAM FIBER", "airtelbroadband@payu", "ACCT 20087654"),
              1199, "debit", "Essentials", "Bills", "Internet"),
        g.txn(g.jday(m, 7, 10), m, g.upi("TSSPDCL", "billpay.tsspdcl@icici", "USN 998877665544"),
              g.amt(700, 1100) if m <= 3 else g.amt(1600, 2400), "debit", "Essentials", "Bills", "Electricity"),
    ]
    if m in (1, 3, 6):  # invests only after good-income months
        rows += [
            g.txn(g.jday(m, 20, 24), m, "ACH D-INDIAN CLEARING CORP-PARAG PARIKH FLEXI CAP-IN{r}".format(r=g.ref12()),
                  5000, "debit", "Goals", "Investment", "Emergency Fund"),
            g.txn(g.jday(m, 20, 24), m, "IB BILLPAY DR-NPS TIER1 CRA-PRAN XXXX9012",
                  5000, "debit", "Goals", "Investment", "NPS"),
        ]
    return rows


def one_offs(g, m):
    rows = []
    if m == 1:  # GST Q3 + health insurance quarterly
        rows += [
            g.txn(11, 1, "IB BILLPAY DR-GSTN PAYMENT-GSTIN 36ABCPK1234F1Z5-Q3 FY25-26",
                  9400, "debit", "Essentials", "Tax", "GST"),
            g.txn(20, 1, "ACH D-NIVA BUPA HEALTH-POL NB2026009988-QTRLY PREMIUM",
                  5500, "debit", "Essentials", "Insurance", "Health"),
        ]
    if m == 2:  # gear purchase + client dinner
        rows += [
            g.txn(13, 2, "POS 453210XXXXXX1122 AMAZON IN SSD 1TB",
                  6500, "debit", "Lifestyle", "Shopping", "Electronics"),
            g.txn(21, 2, g.upi("OHRIS JIVA", "ohris.jubilee@okhdfcbank", "CLIENT MEETING DINNER"),
                  900, "debit", "Lifestyle", "Food & Drinks", "Eating Out"),
        ]
    if m == 3:  # advance tax + portfolio site renewal
        rows += [
            g.txn(15, 3, "IB BILLPAY DR-INCOME TAX-ADVANCE TAX AY2026-27-CIN{r}".format(r=g.ref12()),
                  12000, "debit", "Essentials", "Tax", "Income Tax"),
            g.txn(22, 3, "POS 453210XXXXXX1122 GODADDY DOMAIN HOSTING",
                  3499, "debit", "Goals", "Business", "Software"),
        ]
    if m == 4:  # dry month: GST + insurance still due, deliverables couriered
        rows += [
            g.txn(11, 4, "IB BILLPAY DR-GSTN PAYMENT-GSTIN 36ABCPK1234F1Z5-Q4 FY25-26",
                  8200, "debit", "Essentials", "Tax", "GST"),
            g.txn(20, 4, "ACH D-NIVA BUPA HEALTH-POL NB2026009988-QTRLY PREMIUM",
                  5500, "debit", "Essentials", "Insurance", "Health"),
            g.txn(17, 4, g.upi("DTDC COURIER KONDAPUR", "dtdc.kondapur@paytm", "CLIENT PROOFS DISPATCH"),
                  480, "debit", "Goals", "Business", "Logistics"),
        ]
    if m == 5:  # upskilling course
        rows += [
            g.txn(9, 5, "POS 453210XXXXXX1122 UDEMY ONLINE COURSE",
                  2999, "debit", "Lifestyle", "Personal", "Hobbies"),
        ]
    if m == 6:  # ergonomic chair after good months
        rows += [
            g.txn(14, 6, g.upi("FEATHERLITE STORE", "featherlite.hyd@okaxis", "ERGO OFFICE CHAIR"),
                  5499, "debit", "Lifestyle", "Home", "Essentials"),
        ]
    return rows


def variable_pool(g, m):
    """Weighted everyday spends; single freelancer, chai + metro heavy."""
    return [
        (6, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("KUMARI VEGETABLES", "9848765432@ybl", "VEGETABLES"),
                          g.amt(60, 250, 10), "debit", "Essentials", "Groceries", "Vegetables")),
        (3, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("ZEPTO", "zepto.marketplace@axisb", "ORDER Z{r}".format(r=g.ref12()[:8])),
                          g.amt(400, 900, 10), "debit", "Essentials", "Groceries", "Staples")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("SRI BALAJI FRUITS", "9700554433@paytm", "FRUITS"),
                          g.amt(100, 300, 10), "debit", "Essentials", "Groceries", "Fruits")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("FRESH EGGS MART", "freshmart.gachibowli@okicici", "EGGS BREAD"),
                          g.amt(120, 240, 10), "debit", "Essentials", "Groceries", "Eggs")),
        (6, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("NIMRAH IRANI CAFE", "nimrah.cafe@ybl", "CHAI OSMANIA"),
                          g.amt(30, 110, 10), "debit", "Lifestyle", "Food & Drinks", "Tea & Coffee")),
        (4, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("SWIGGY", "swiggy@icici", "ORDER {r}".format(r=g.ref12()[:8])),
                          g.amt(200, 480, 10), "debit", "Lifestyle", "Food & Drinks", "Take Away")),
        (3, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("ZOMATO", "zomato.order@hdfcbank", "ORDER {r}".format(r=g.ref12()[:8])),
                          g.amt(220, 520, 10), "debit", "Lifestyle", "Food & Drinks", "Fast Food")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("CAFE NILOUFER", "niloufer.lakdikapul@okaxis", "LUNCH"),
                          g.amt(300, 650, 10), "debit", "Lifestyle", "Food & Drinks", "Eating Out")),
        (4, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("L&T METRO RAIL", "ltmetro.recharge@icici", "SMART CARD TOPUP"),
                          g.amt(100, 300, 50), "debit", "Essentials", "Transport", "Train")),
        (4, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("RAPIDO BIKE TAXI", "rapido@ybl", "RIDE"),
                          g.amt(50, 150, 10), "debit", "Essentials", "Transport", "Rapido")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("AUTO STAND GACHIBOWLI", "9963887744@paytm", "AUTO FARE"),
                          g.amt(60, 160, 10), "debit", "Essentials", "Transport", "Auto")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, "POS 453210XXXXXX1122 HP PETROL BIKE FUEL",
                          g.amt(300, 500, 50), "debit", "Essentials", "Transport", "Fuel")),
        (1, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("DTDC COURIER KONDAPUR", "dtdc.kondapur@paytm", "CLIENT DISPATCH"),
                          g.amt(250, 600, 10), "debit", "Goals", "Business", "Logistics")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("MEDPLUS PHARMACY", "medplus.madhapur@icici", "MEDICINES"),
                          g.amt(150, 450, 10), "debit", "Essentials", "Medical", "Medicines")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, "POS 453210XXXXXX1122 RATNADEEP SUPER MARKET",
                          g.amt(250, 600, 10), "debit", "Lifestyle", "Home", "Toiletries")),
        (1, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("LOOKS SALON", "9848112299@okaxis", "HAIRCUT BEARD"),
                          g.amt(200, 400, 50), "debit", "Lifestyle", "Personal", "Grooming")),
        (1, lambda: g.txn(g.jday(m, 1, 28), m, "POS 453210XXXXXX1122 AMB CINEMAS GACHIBOWLI",
                          g.amt(300, 600, 50), "debit", "Lifestyle", "Entertainment", "Movies")),
        (1, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("SRI SAI SNACKS", "9885443322@ybl", "SAMOSA CHAT"),
                          g.amt(50, 180, 10), "debit", "Lifestyle", "Food & Drinks", "Snacks")),
    ]


if __name__ == "__main__":
    run(Gen(SEED), MONTHS, TARGET_PER_MONTH, fixed_monthly, one_offs, variable_pool, OUT)
