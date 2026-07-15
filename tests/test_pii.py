"""Unit tests for the PII pseudonymization layer, using real narration shapes
from the synthetic seed data."""

from pii.pseudonymizer import Pseudonymizer, detect_pii


def test_detects_vpa_not_phone_inside_it():
    hits = detect_pii("UPI-624731781080-RAMULU VEGETABLES-9701234567@ybl-VEGETABLES")
    assert ("vpa", "9701234567@ybl") in hits
    assert all(t != "phone" for t, _ in hits)  # phone digits belong to the VPA


def test_detects_standalone_phone_and_vpa_separately():
    hits = detect_pii("UPI-111122223333-AIRTEL POSTPAID-9848012345@airtel-BILL 9848012345")
    assert ("vpa", "9848012345@airtel") in hits
    assert ("phone", "9848012345") in hits


def test_detects_masked_card_and_account():
    assert ("card", "416021XXXXXX8907") in detect_pii("POS 416021XXXXXX8907 DMART")
    assert ("account", "XXXXXX4521") in detect_pii("IMPS-P2A-RAJESHWAR RAO-XXXXXX4521-SUPPORT")


def test_detects_every_loan_ref_format_in_the_seed():
    assert ("loan_ref", "LN00458912337") in detect_pii(
        "ACH D-HDFC LTD HOME LOAN-LN00458912337-EMI")
    assert ("loan_ref", "LVHYD00812345") in detect_pii(
        "ACH D-ICICI BANK VEHICLE LOAN-LVHYD00812345-EMI")
    assert ("loan_ref", "L2XN887766") in detect_pii(
        "ACH D-BAJAJ FINSERV-LAPTOP LOAN L2XN887766-EMI")


def test_detects_policy_numbers():
    assert ("policy", "667788990") in detect_pii(
        "UPI-214188805929-LIC OF INDIA-licindia.premium@sbi-POL 667788990 QTRLY")
    assert ("policy", "SH2026114455") in detect_pii(
        "ACH D-STAR HEALTH INSURANCE-POL SH2026114455-QTRLY PREMIUM")


def test_oneoff_txn_refs_are_out_of_scope():
    # NEFT/ACH/CIN ids identify a transaction, not a person: out of scope
    assert detect_pii("NEFT CR-HDFC0000123-TECHNOVA-SALARY-N104332181960") == []
    assert detect_pii("IB BILLPAY DR-INCOME TAX-CIN709682506710") == []


def test_twelve_digit_ref_is_not_a_phone():
    # UPI refs are 12 digits; the 10-digit phone pattern must not fire inside
    assert detect_pii("UPI-615594078161-SOME MERCHANT-PAYMENT") == []


def test_pseudonymize_replaces_all_and_is_consistent():
    p = Pseudonymizer(user_id=1)
    t1 = p.pseudonymize("UPI-999-SCHOOL-littleflower.fees@okaxis-FEE JAN")
    t2 = p.pseudonymize("UPI-888-SCHOOL-littleflower.fees@okaxis-FEE FEB")
    assert "littleflower.fees@okaxis" not in t1
    fake = p.mapping["littleflower.fees@okaxis"][1]
    assert fake in t1 and fake in t2  # same fake both times


def test_no_raw_pii_survives():
    p = Pseudonymizer(user_id=3)
    raw = "NWD-489377XXXXXX3321-ATM CASH-9912665544-XXXXXX3344 9701234567@ybl"
    out = p.pseudonymize(raw)
    for real in ("489377XXXXXX3321", "9912665544", "XXXXXX3344", "9701234567@ybl"):
        assert real not in out


def test_mappings_are_isolated_per_user():
    p1 = Pseudonymizer(user_id=1)
    p2 = Pseudonymizer(user_id=2)
    real = "9848012345"
    f1 = p1.pseudonymize(f"BILL {real}")
    f2 = p2.pseudonymize(f"BILL {real}")
    assert p1.mapping[real][1] != p2.mapping[real][1]
    assert f1 != f2
