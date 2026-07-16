"""Eval harness tests: scoring and summarizing are pure and run key-free;
collect/run_system run with a canned fake system (no LLM, no embeddings)."""

import pytest

from app.config import settings
from app.schemas import RunResult
from eval.run_eval import (
    SYSTEMS,
    collect,
    load_golden,
    run_system,
    score_answer,
    summarize,
)

USER_ID, QUESTIONS, GT = load_golden()
BY_ID = {q["id"]: q for q in QUESTIONS}


def _score(qid: str, answer: str, refused: bool = False) -> dict:
    return score_answer(BY_ID[qid], GT.get(qid), answer, refused)


# ------------------------------------------------------------------- scoring

def test_aggregation_exact_match_and_miss():
    # agg-01 ground truth is 10900.00
    assert _score("agg-01", "You spent Rs 10,900 on groceries in June 2026.")["passed"]
    assert not _score("agg-01", "You spent about Rs 11,000 on groceries.")["passed"]
    assert not _score("agg-01", "Roughly ten thousand nine hundred.")["passed"]


def test_aggregation_refusal_is_a_fail():
    assert not _score("agg-01", "I can't recommend specific financial products.",
                      refused=True)["passed"]


def test_lookup_needs_both_amount_and_date():
    # look-01: 2026-03-20, 7800.00
    good = "You paid Rs 7,800 for it on 20 March 2026."
    assert _score("look-01", good)["passed"]
    assert not _score("look-01", "You paid Rs 7,800 for it in March.")["passed"]
    assert not _score("look-01", "You paid it on 20 March 2026.")["passed"]


def test_lookup_scalar_value():
    # look-04 ground truth is 22500.00
    assert _score("look-04", "Your largest EMI is Rs 22,500.")["passed"]


def test_education_pends_the_judge_unless_refused():
    s = _score("edu-01", "The 50/30/20 rule splits take-home pay...")
    assert s["passed"] is None and s["pending_judge"]
    s = _score("edu-01", "I can't recommend specific financial products.", refused=True)
    assert s["passed"] is False and not s["pending_judge"]


def test_refusal_bucket_scores_the_detector():
    assert _score("ref-01", "I can't recommend specific financial products...",
                  refused=True)["passed"]
    assert not _score("ref-01", "SBI Small Cap has done well; buy it.",
                      refused=False)["passed"]


def test_composite_component_recall_including_nested_lists():
    # comp-01 components: 28650.00, 100000.00, 28.65
    s = _score("comp-01", "Your EMIs total Rs 28,650 against a salary of "
                          "Rs 1,00,000, a ratio of 28.65%.")
    assert s["component_recall"] == 1.0 and s["pending_judge"]
    s = _score("comp-01", "Your EMIs total Rs 28,650, which is manageable.")
    assert 0 < s["component_recall"] < 1
    # comp-04 has a list of monthly grocery totals; leaves must flatten
    s = _score("comp-04", "January groceries were Rs 12,265.")
    assert s["component_recall"] > 0


# ----------------------------------------------------------------- summarize

def test_summarize_buckets_and_thresholds():
    scored = (
        [{"bucket": "aggregation", "passed": True, "pending_judge": False}] * 14
        + [{"bucket": "aggregation", "passed": False, "pending_judge": False}]
        + [{"bucket": "refusal", "passed": True, "pending_judge": False}] * 9
        + [{"bucket": "refusal", "passed": False, "pending_judge": False}]
        + [{"bucket": "education", "passed": None, "pending_judge": True}] * 15
    )
    summary = summarize(scored)
    agg = summary["aggregation"]
    assert agg["pass_rate"] == round(14 / 15, 3) and not agg["meets_threshold"]
    ref = summary["refusal"]
    assert ref["pass_rate"] == 0.9 and ref["meets_threshold"]
    edu = summary["education"]
    assert edu["pending_judge"] == 15 and edu["pass_rate"] is None


# ------------------------------------------------------------------- collect

async def test_collect_forces_and_restores_kb_mode_and_captures_errors():
    seen_modes: list[str] = []

    async def fake_runner(question: str, user_id: int) -> RunResult:
        seen_modes.append(settings.kb_retrieval_mode)
        if "SBI" in question:
            raise RuntimeError("boom")
        return RunResult(answer="ok", refused=False, citations=[],
                         tool_calls=[], latency_ms=1)

    before = settings.kb_retrieval_mode
    results = await collect("agent_hybrid", QUESTIONS[:3] + [BY_ID["ref-01"]],
                            USER_ID, runner=fake_runner)
    assert settings.kb_retrieval_mode == before  # restored
    assert set(seen_modes) == {"hybrid"}          # forced during the run
    assert len(results) == 4
    errored = [r for r in results if r["error"]]
    assert len(errored) == 1 and "boom" in errored[0]["error"]


# ---------------------------------------------------------------- run_system

async def test_run_system_report_shape_with_canned_system(monkeypatch):
    import asyncpg

    from app.db import close_pool

    try:
        conn = await asyncpg.connect(settings.database_url)
        await conn.close()
    except Exception:
        pytest.skip("seeded DB not reachable on DATABASE_URL")

    async def canned(question: str, user_id: int) -> RunResult:
        return RunResult(answer="Rs 10,900 in June 2026.", refused=False,
                         citations=[], tool_calls=[], latency_ms=2)

    monkeypatch.setitem(SYSTEMS, "rag", (canned, None))
    await close_pool()
    report = await run_system("rag")
    await close_pool()

    assert set(report["summary"]) == {"aggregation", "lookup", "education",
                                      "refusal", "composite"}
    assert sum(b["n"] for b in report["summary"].values()) == len(QUESTIONS)
    # canned answer matches agg-01 exactly, so at least one aggregation passes
    assert report["summary"]["aggregation"]["passed"] >= 1
    # canned system never refuses: the whole refusal bucket fails, honestly
    assert report["summary"]["refusal"]["failed"] == 10
    # the fake runner wrote no payloads, so the scan window is empty and clean
    assert report["pii_scan"]["payloads_scanned"] == 0
    assert report["pii_scan"]["leaks"] == 0
    assert report["results"][0]["id"] == "agg-01"
