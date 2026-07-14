"""Generate synthetic 6-month transaction CSV for user3 (youngRenter persona).

26-year-old single techie, Rs 60,000/month salary, rented 1BHK, lifestyle
heavy: BNPL (Simpl/Slice/LazyPay) + credit card, pet cat, gym, food delivery
15x/month. Includes the aggregation traps: monthly Self Transfer to own
savings and money Lent to friends (must not be counted as consumption),
plus a Gift row and a loan-repayment credit. Seed 99.

Usage: python3 fake-data/generate_user3.py
"""

from pathlib import Path

from genlib import MONTH_NAMES, Gen, run

SEED = 99
MONTHS = [1, 2, 3, 4, 5, 6]
TARGET_PER_MONTH = 60
OUT = Path(__file__).parent / "user3_youngrenter_transactions.csv"


def fixed_monthly(g, m):
    return [
        g.txn(1, m, f"NEFT CR-ICIC0004321-QUBERT TECHNOLOGIES PVT LTD-SALARY {MONTH_NAMES[m]} {g.year}-N{g.ref12()}",
              60000, "credit"),
        g.txn(2, m, g.upi("VENKAT RAO", "venkatrao.landlord@oksbi", "1BHK RENT MADHAPUR"),
              15000, "debit", "Essentials", "Bills", "Rent"),
        g.txn(3, m, g.upi("SLICE", "slice.repay@axisb", "SLICE CARD BILL"),
              g.amt(2000, 3200, 50), "debit", "Essentials", "Credit Bill", "Slice"),
        g.txn(5, m, g.upi("SIMPL", "getsimpl@ybl", "SIMPL DUES CLEARED"),
              g.amt(900, 1600, 50), "debit", "Essentials", "Credit Bill", "Simpl"),
        g.txn(7, m, g.upi("LAZYPAY", "lazypay.payu@hdfcbank", "LAZYPAY BILL"),
              g.amt(600, 1200, 50), "debit", "Essentials", "Credit Bill", "LazyPay"),
        g.txn(15, m, "SI DEBIT-AXIS BANK CC XXXXXX5566-AUTOPAY STATEMENT DUE",
              g.amt(8000, 12000, 100), "debit", "Essentials", "Credit Bill", "Credit Card"),
        g.txn(5, m, g.upi("GOLDS GYM MADHAPUR", "goldsgym.madhapur@okicici", "MONTHLY MEMBERSHIP"),
              1500, "debit", "Lifestyle", "Fitness", "Gym"),
        g.txn(g.jday(m, 8, 12), m, g.upi("SUPERTAILS", "supertails@icici", "CAT FOOD LITTER ORDER"),
              1250, "debit", "Lifestyle", "Pet Care", "Food"),
        g.txn(g.jday(m, 15, 18), m, "POS 489377XXXXXX3321 NETFLIX COM MUMBAI",
              649, "debit", "Lifestyle", "Subscription", "Netflix"),
        g.txn(g.jday(m, 15, 18), m, "POS 489377XXXXXX3321 SPOTIFY INDIA PREMIUM",
              119, "debit", "Lifestyle", "Subscription", "Others"),
        g.txn(25, m, f"IMPS-P2A-{g.ref12()}-SANDEEP SELF-XXXXXX3344-TO SAVINGS AC",
              5000, "debit", "Goals", "Self Transfer", ""),
        g.txn(g.jday(m, 9, 12), m, f"UPI-{g.ref12()}-JIO PREPAID-7013456789@jio-RECHARGE 7013456789",
              399, "debit", "Essentials", "Bills", "Phone"),
        g.txn(g.jday(m, 10, 14), m, g.upi("JIOFIBER", "jiofiber.bill@sbi", "ACCT 30011223"),
              799, "debit", "Essentials", "Bills", "Internet"),
        g.txn(g.jday(m, 6, 9), m, g.upi("TSSPDCL", "billpay.tsspdcl@icici", "USN 556677889900"),
              g.amt(500, 900) if m <= 3 else g.amt(1100, 1700), "debit", "Essentials", "Bills", "Electricity"),
    ]


def one_offs(g, m):
    rows = []
    if m == 1:  # new year party + steam sale + winter sale jacket
        rows += [
            g.txn(1, 1, g.upi("SOCIAL HITEC CITY", "social.hitec@okhdfcbank", "NYE PARTY SPLIT"),
                  2000, "debit", "Lifestyle", "Events", "Party"),
            g.txn(10, 1, "POS 489377XXXXXX3321 STEAMGAMES COM",
                  2499, "debit", "Lifestyle", "Shopping", "Video Games"),
            g.txn(18, 1, "POS 489377XXXXXX3321 MYNTRA EORS SALE",
                  1999, "debit", "Lifestyle", "Shopping", "Clothes"),
        ]
    if m == 2:  # Gokarna weekend + valentine dinner + lends to friend
        rows += [
            g.txn(13, 2, g.upi("ABHIBUS", "abhibus@icici", "HYD GOKARNA SLEEPER"),
                  1400, "debit", "Lifestyle", "Travel", "Commute"),
            g.txn(14, 2, g.upi("ZOSTEL GOKARNA", "zostel.gokarna@okaxis", "2N DORM STAY"),
                  2400, "debit", "Lifestyle", "Travel", "Hotel"),
            g.txn(15, 2, g.upi("NAMASTE CAFE GOKARNA", "9448765521@ybl", "BEACH SHACK MEALS"),
                  900, "debit", "Lifestyle", "Travel", "Meals"),
            g.txn(15, 2, g.upi("KUDLE ADVENTURES", "kudle.kayak@paytm", "KAYAKING SESSION"),
                  1200, "debit", "Lifestyle", "Travel", "Activities"),
            g.txn(21, 2, f"IMPS-P2A-{g.ref12()}-ROHIT KUMAR-XXXXXX8890-EMERGENCY HELP",
                  3000, "debit", "Goals", "Lent", ""),
        ]
    if m == 3:  # holi party + sneakers + cat vet
        rows += [
            g.txn(4, 3, g.upi("PLAYARENA HOLI BASH", "playarena.events@okicici", "HOLI PARTY PASS"),
                  1500, "debit", "Lifestyle", "Events", "Party"),
            g.txn(14, 3, "POS 489377XXXXXX3321 NIKE STORE FORUM MALL",
                  3499, "debit", "Lifestyle", "Shopping", "Footwear"),
            g.txn(22, 3, g.upi("PAWS N CLAWS CLINIC", "pawsnclaws.vet@okhdfcbank", "CAT VACCINATION"),
                  800, "debit", "Lifestyle", "Pet Care", "Vet"),
        ]
    if m == 4:  # IPL night + cat grooming + summer wear
        rows += [
            g.txn(12, 4, g.upi("DISTRICT TICKETS", "district.paytm@paytm", "IPL SRH MATCH UPPAL"),
                  1800, "debit", "Lifestyle", "Entertainment", "Tickets"),
            g.txn(19, 4, g.upi("PETSPOT SPA", "petspot.madhapur@ybl", "CAT GROOMING"),
                  600, "debit", "Lifestyle", "Pet Care", "Grooming"),
            g.txn(26, 4, "POS 489377XXXXXX3321 ZUDIO KUKATPALLY",
                  2200, "debit", "Lifestyle", "Shopping", "Clothes"),
        ]
    if m == 5:  # concert + another lend + badminton tournament
        rows += [
            g.txn(9, 5, "POS 489377XXXXXX3321 BOOKMYSHOW ARIJIT LIVE",
                  1999, "debit", "Lifestyle", "Entertainment", "Shows"),
            g.txn(17, 5, f"IMPS-P2A-{g.ref12()}-ANIRUDH V-XXXXXX6677-TILL SALARY",
                  2000, "debit", "Goals", "Lent", ""),
            g.txn(24, 5, g.upi("PLAYO SPORTS", "playo@axisb", "CORPORATE TOURNEY ENTRY"),
                  500, "debit", "Lifestyle", "Fitness", "Badminton"),
        ]
    if m == 6:  # steam summer sale + gift for mom + friend repays feb loan
        rows += [
            g.txn(26, 6, "POS 489377XXXXXX3321 STEAMGAMES SUMMER SALE",
                  1999, "debit", "Lifestyle", "Shopping", "Video Games"),
            g.txn(14, 6, g.upi("ARCHIES GALLERY", "archies.forum@okaxis", "MOM BIRTHDAY GIFT"),
                  1500, "debit", "Goals", "Gift", ""),
            g.txn(30, 6, f"IMPS-P2A-CR-{g.ref12()}-ROHIT KUMAR-XXXXXX8890-LOAN REPAYMENT",
                  3000, "credit"),
        ]
    return rows


def variable_pool(g, m):
    """Weighted everyday spends; delivery-app heavy single lifestyle."""
    return [
        (8, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("SWIGGY", "swiggy@icici", "ORDER {r}".format(r=g.ref12()[:8])),
                          g.amt(280, 650, 10), "debit", "Lifestyle", "Food & Drinks", "Take Away")),
        (6, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("ZOMATO", "zomato.order@hdfcbank", "ORDER {r}".format(r=g.ref12()[:8])),
                          g.amt(300, 700, 10), "debit", "Lifestyle", "Food & Drinks", "Fast Food")),
        (5, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("BLINKIT", "blinkit.grocery@ybl", "ORDER B{r}".format(r=g.ref12()[:8])),
                          g.amt(300, 800, 10), "debit", "Essentials", "Groceries", "Staples")),
        (4, lambda: g.txn(g.jday(m, 1, 28), m, "POS 489377XXXXXX3321 THIRD WAVE COFFEE",
                          g.amt(250, 420, 10), "debit", "Lifestyle", "Food & Drinks", "Tea & Coffee")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("ABS ABSOLUTE BARBECUE", "absbarbecue.hitec@okhdfcbank", "BUFFET"),
                          g.amt(800, 1400, 50), "debit", "Lifestyle", "Food & Drinks", "Eating Out")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("MAGGI POINT KPHB", "9959887766@ybl", "MIDNIGHT SNACKS"),
                          g.amt(150, 350, 10), "debit", "Lifestyle", "Food & Drinks", "Snacks")),
        (4, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("UBER INDIA", "uber.rides@axisb", "TRIP {r}".format(r=g.ref12()[:8])),
                          g.amt(150, 450, 10), "debit", "Essentials", "Transport", "Uber")),
        (4, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("RAPIDO BIKE TAXI", "rapido@ybl", "RIDE"),
                          g.amt(60, 180, 10), "debit", "Essentials", "Transport", "Rapido")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("AUTO STAND MADHAPUR", "9912665544@paytm", "AUTO FARE"),
                          g.amt(60, 150, 10), "debit", "Essentials", "Transport", "Auto")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("TONIQUE WINES", "tonique.jubilee@okicici", "WEEKEND STOCK"),
                          g.amt(700, 1600, 50), "debit", "Lifestyle", "Personal", "Vices")),
        (2, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("PLAYO SPORTS", "playo@axisb", "BADMINTON COURT 1HR"),
                          g.amt(300, 500, 50), "debit", "Lifestyle", "Fitness", "Badminton")),
        (1, lambda: g.txn(g.jday(m, 1, 28), m, "POS 489377XXXXXX3321 PVR NEXUS MALL",
                          g.amt(500, 800, 50), "debit", "Lifestyle", "Entertainment", "Movies")),
        (1, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("APOLLO PHARMACY", "apollopharmacy@icici", "MEDICINES"),
                          g.amt(150, 400, 10), "debit", "Essentials", "Medical", "Medicines")),
        (1, lambda: g.txn(g.jday(m, 1, 28), m, "POS 489377XXXXXX3321 RATNADEEP SUPER MARKET",
                          g.amt(400, 800, 10), "debit", "Lifestyle", "Home", "Toiletries")),
        (1, lambda: g.txn(g.jday(m, 1, 28), m, g.upi("URBAN COMPANY", "urbancompany@axisb", "HOME DEEP CLEAN"),
                          g.amt(700, 1000, 50), "debit", "Lifestyle", "Home", "Cleaning")),
    ]


if __name__ == "__main__":
    run(Gen(SEED), MONTHS, TARGET_PER_MONTH, fixed_monthly, one_offs, variable_pool, OUT)
