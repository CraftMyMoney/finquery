"""Static integrity checks for the golden set (no DB needed).
DB-dependent verification happens in eval/compute_ground_truth.py, which
fails loudly if any stored SQL returns nothing."""

import json
from pathlib import Path

import pytest

GOLDEN = json.loads(
    (Path(__file__).resolve().parent.parent / "eval" / "golden_set.json").read_text()
)
QUESTIONS = GOLDEN["questions"]


def test_bucket_counts_match_design():
    counts: dict[str, int] = {}
    for q in QUESTIONS:
        counts[q["bucket"]] = counts.get(q["bucket"], 0) + 1
    assert counts == GOLDEN["buckets"] == {
        "aggregation": 15, "lookup": 10, "education": 15, "refusal": 10, "composite": 5,
    }
    assert len(QUESTIONS) == 55


def test_ids_unique_and_prefixed_by_bucket():
    ids = [q["id"] for q in QUESTIONS]
    assert len(ids) == len(set(ids))
    prefix = {"aggregation": "agg-", "lookup": "look-", "education": "edu-",
              "refusal": "ref-", "composite": "comp-"}
    for q in QUESTIONS:
        assert q["id"].startswith(prefix[q["bucket"]]), q["id"]


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["id"])
def test_required_fields_per_bucket(q):
    assert q["question"].strip().endswith("?") or q["bucket"] == "refusal"
    if q["bucket"] in ("aggregation", "lookup"):
        assert q["answer_type"] in ("number", "row", "rows")
        assert q["ground_truth_sql"].lstrip().upper().startswith("SELECT")
    elif q["bucket"] == "education":
        assert len(q["expected_points"]) >= 2
        assert q["expected_source"].startswith("kb/")
    elif q["bucket"] == "refusal":
        assert q["expect_refusal"] is True
        assert q["why"]
    elif q["bucket"] == "composite":
        assert len(q["components"]) >= 2
        for comp in q["components"]:
            assert comp["sql"].lstrip().upper().startswith("SELECT")
            assert comp["answer_type"] in ("number", "row", "rows")
        assert len(q["expected_concepts"]) >= 2


def test_all_sql_is_scoped_to_user1():
    for q in QUESTIONS:
        sqls = [q.get("ground_truth_sql")] + [c["sql"] for c in q.get("components", [])]
        for sql in filter(None, sqls):
            assert "user_id = 1" in sql, f"{q['id']}: SQL not scoped to user 1"


def test_education_sources_exist():
    root = Path(__file__).resolve().parent.parent
    for q in QUESTIONS:
        src = q.get("expected_source")
        if src:
            assert (root / src).is_file(), f"{q['id']}: missing {src}"
