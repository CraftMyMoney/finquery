"""Refusal detector and criteria-text tests. Key-independent: the detector is
deterministic string matching; whether the LLM actually refuses is measured
by the eval harness against the 10 refusal probes."""

from guardrails.refusal import REFUSAL_CRITERIA, REFUSAL_MARKER, is_refusal


def test_criteria_text_instructs_the_marker_and_both_sides_of_the_line():
    assert REFUSAL_MARKER in REFUSAL_CRITERIA
    assert "SEBI-registered" in REFUSAL_CRITERIA
    # both halves of the specificity filter must be spelled out
    assert "must refuse" in REFUSAL_CRITERIA
    assert "must not refuse" in REFUSAL_CRITERIA
    assert "specificity, not topic" in REFUSAL_CRITERIA


def test_marked_refusal_is_detected():
    reply = (f"{REFUSAL_MARKER}. Picking a fund requires a SEBI-registered "
             "investment adviser. I can explain what small-cap funds are instead.")
    assert is_refusal(reply)


def test_unmarked_refusal_phrasings_are_detected():
    assert is_refusal("I cannot recommend specific stocks, but I can explain "
                      "how to evaluate the category.")
    assert is_refusal("Sorry, I'm unable to recommend specific mutual funds.")
    assert is_refusal("I can’t advise on specific products like that NFO.")


def test_education_answer_with_benign_recommend_is_not_a_refusal():
    reply = ("Many planners recommend saving at least 20 percent of income. "
             "The 50/30/20 rule splits take-home pay into needs, wants and savings.")
    assert not is_refusal(reply)


def test_trailing_adviser_disclaimer_does_not_count():
    reply = ("An ELSS is an equity-linked savings scheme with a three year "
             "lock-in and Section 80C benefits up to 1.5 lakh per year. "
             "Compared to PPF it is market-linked, so returns vary, and "
             "compared to NPS it has the shortest lock-in of the three. "
             "Your own transactions show a 4,000 rupee monthly ELSS SIP. "
             "For choosing a particular scheme, please consult a "
             "SEBI-registered investment adviser; I can't recommend specific "
             "financial products.")
    assert not is_refusal(reply)


def test_numeric_analysis_of_users_own_data_is_not_a_refusal():
    reply = ("Your EMIs total 28,650 per month against a salary of 1,00,000, "
             "a debt-to-income ratio of 28.65 percent, which is under the 30 "
             "percent guideline.")
    assert not is_refusal(reply)
