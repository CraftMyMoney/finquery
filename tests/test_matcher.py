"""Numeric matcher tests: every rupee format the systems are likely to emit
must resolve to the same Decimal as the SQL-derived ground truth."""

from decimal import Decimal

from eval.matcher import extract_numbers, numeric_match


def test_formats_all_match_the_same_ground_truth():
    for answer in (
        "You spent Rs 10,900 on groceries in June.",
        "You spent ₹10,900.00 on groceries.",
        "Groceries in June 2026 came to 10900 rupees.",
        "INR 10,900.00 total.",
    ):
        assert numeric_match("10900.00", answer), answer


def test_indian_two_digit_grouping():
    assert numeric_match("100812.00", "Your March income was Rs 1,00,812.")
    assert numeric_match("171900.00", "EMIs totalled ₹1,71,900 over six months.")


def test_percent_and_count_values():
    assert numeric_match("28.65", "Your EMI ratio is 28.65% of income.")
    assert numeric_match(17, "You took 17 Uber rides in that period.")


def test_wrong_number_does_not_match():
    assert not numeric_match("10900.00", "You spent Rs 10,090 on groceries.")
    assert not numeric_match("10900.00", "You spent Rs 109,000 on groceries.")


def test_number_inside_dates_and_ids_does_not_leak_a_false_match():
    text = "Between 2026-06-01 and 2026-06-30 (txn 109003) you spent Rs 500."
    numbers = extract_numbers(text)
    assert Decimal("10900.00") not in numbers
    assert Decimal("500") in numbers


def test_extraction_handles_mixed_prose():
    text = ("May spending was ₹1,20,960.00 against income of Rs 1,00,000; "
            "Travel alone was 15,150 versus a 1,500 budget, 13,650 over.")
    numbers = extract_numbers(text)
    for expected in ("120960.00", "100000", "15150", "1500", "13650"):
        assert Decimal(expected) in numbers, expected
