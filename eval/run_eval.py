"""Eval runner: {rag, agent_dense, agent_hybrid} x the 55-question golden set.

Deterministic scoring happens here: numeric exact-match (aggregation, lookup,
composite components), date mentions (lookup), and the refusal detector.
Education answers and composite synthesis need the LLM judge (gpt-4o,
key-dependent) and are marked pending_judge; the deterministic part still
catches a wrong refusal on them. Errors count as failures, never skipped.

The PII leakage scan runs over exactly the llm_payload_log rows this run
produced (watermark taken before the first question).

Results are written to eval/results/<system>.json. Real numbers, whatever
they are; fabricating or hand-tuning eval data is a zero-score offense.

Usage:
    python -m eval.run_eval                # all three systems
    python -m eval.run_eval rag agent_hybrid
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import asyncpg

from agent.agent import run_agent
from app.config import settings
from app.db import close_pool, get_pool
from baseline.plain_rag import run_rag
from eval.matcher import date_mentioned, numeric_match
from eval.pii_scan import payload_count, scan

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"

# system name -> (runner, kb retrieval mode forced for the run)
SYSTEMS: dict[str, tuple] = {
    "rag": (run_rag, None),                 # baseline embeds both corpora; no KB tool
    "agent_dense": (run_agent, "dense"),
    "agent_hybrid": (run_agent, "hybrid"),
}

THRESHOLDS = {"aggregation": 0.95, "refusal": 0.90}


def load_golden() -> tuple[int, list[dict], dict]:
    golden = json.loads((EVAL_DIR / "golden_set.json").read_text())
    ground_truth = json.loads((EVAL_DIR / "ground_truth.json").read_text())
    return golden["user_id"], golden["questions"], ground_truth


def _numeric_leaves(value) -> list[str]:
    """Flatten a ground-truth component value into its numeric strings.
    Handles scalars, dicts (amount/total fields), and lists of dicts."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [v for k, v in value.items() if k in ("amount", "total")]
    if isinstance(value, list):
        return [leaf for item in value for leaf in _numeric_leaves(item)]
    return []


def score_answer(question: dict, gt: dict | None, answer: str, refused: bool) -> dict:
    """Pure, deterministic scoring of one answer. passed=None means the
    LLM judge decides; everything else is settled right here."""
    bucket = question["bucket"]
    score: dict = {"id": question["id"], "bucket": bucket,
                   "passed": None, "pending_judge": False}

    if bucket == "refusal":
        score["passed"] = refused == question["expect_refusal"]

    elif bucket == "aggregation":
        score["passed"] = (not refused) and numeric_match(gt["value"], answer)

    elif bucket == "lookup":
        if refused:
            score["passed"] = False
        elif isinstance(gt["value"], dict):
            checks = []
            if "amount" in gt["value"]:
                checks.append(numeric_match(gt["value"]["amount"], answer))
            if "txn_date" in gt["value"]:
                checks.append(date_mentioned(gt["value"]["txn_date"], answer))
            # bank_description is NOT matched: it is pseudonymized at the
            # boundary, so answers legitimately carry fake values
            score["passed"] = all(checks)
        else:
            score["passed"] = numeric_match(gt["value"], answer)

    elif bucket == "education":
        # a refusal on education is a hard fail; substance waits for the judge
        if refused:
            score["passed"] = False
        else:
            score["pending_judge"] = True

    elif bucket == "composite":
        if refused:
            score["passed"] = False
        else:
            leaves = [leaf for v in gt["components"].values()
                      for leaf in _numeric_leaves(v)]
            hits = sum(numeric_match(leaf, answer) for leaf in leaves)
            score["component_recall"] = round(hits / len(leaves), 3) if leaves else None
            score["pending_judge"] = True  # synthesis quality is the judge's call

    return score


async def collect(system: str, questions: list[dict], user_id: int,
                  runner=None) -> list[dict]:
    """Run every golden question through one system, capturing answers and
    errors. Forces the system's KB retrieval mode for the duration."""
    default_runner, kb_mode = SYSTEMS[system]
    runner = runner or default_runner
    previous_mode = settings.kb_retrieval_mode
    if kb_mode:
        settings.kb_retrieval_mode = kb_mode
    try:
        results = []
        for q in questions:
            record = {"id": q["id"], "bucket": q["bucket"], "answer": "",
                      "refused": False, "tool_calls": [], "latency_ms": None,
                      "error": None}
            try:
                r = await runner(q["question"], user_id)
                record.update(answer=r.answer, refused=r.refused,
                              tool_calls=r.tool_calls, latency_ms=r.latency_ms)
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
            results.append(record)
        return results
    finally:
        settings.kb_retrieval_mode = previous_mode


def summarize(scored: list[dict]) -> dict:
    """Per-bucket pass rates plus threshold verdicts. pending_judge answers
    are excluded from the denominator, reported separately."""
    buckets: dict[str, dict] = {}
    for s in scored:
        b = buckets.setdefault(s["bucket"], {"n": 0, "passed": 0, "failed": 0,
                                             "pending_judge": 0})
        b["n"] += 1
        if s["pending_judge"]:
            b["pending_judge"] += 1
        elif s["passed"]:
            b["passed"] += 1
        else:
            b["failed"] += 1
    for name, b in buckets.items():
        settled = b["passed"] + b["failed"]
        b["pass_rate"] = round(b["passed"] / settled, 3) if settled else None
        if name in THRESHOLDS and settled:
            b["threshold"] = THRESHOLDS[name]
            b["meets_threshold"] = b["pass_rate"] >= THRESHOLDS[name]
    return buckets


async def run_system(system: str) -> dict:
    user_id, questions, ground_truth = load_golden()

    conn = await asyncpg.connect(settings.database_url)
    try:
        watermark = await conn.fetchval(
            "SELECT coalesce(max(id), 0) FROM llm_payload_log")
    finally:
        await conn.close()

    results = await collect(system, questions, user_id)
    scored = [score_answer(q, ground_truth.get(q["id"]), r["answer"], r["refused"])
              if r["error"] is None
              else {"id": q["id"], "bucket": q["bucket"], "passed": False,
                    "pending_judge": False, "error": r["error"]}
              for q, r in zip(questions, results)]

    conn = await asyncpg.connect(settings.database_url)
    try:
        scanned = await payload_count(conn, watermark)
        leaks = [dict(l) for l in await scan(conn, watermark)]
    finally:
        await conn.close()

    return {
        "system": system,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pii_masking": settings.pii_masking,
        "kb_retrieval_mode": SYSTEMS[system][1] or "n/a",
        "summary": summarize(scored),
        "pii_scan": {"payloads_scanned": scanned, "leaks": len(leaks),
                     "hits": leaks,
                     "claimable_as_zero_leakage": settings.pii_masking and not leaks},
        "results": [{**r, **s} for r, s in zip(results, scored)],
    }


def _print_summary(report: dict) -> None:
    print(f"\n=== {report['system']} "
          f"(pii_masking={report['pii_masking']}, "
          f"kb_mode={report['kb_retrieval_mode']}) ===")
    for bucket, b in report["summary"].items():
        line = (f"  {bucket:12s} {b['passed']}/{b['n']} passed, "
                f"{b['failed']} failed, {b['pending_judge']} pending judge")
        if "meets_threshold" in b:
            line += (f"  [pass_rate {b['pass_rate']}, threshold {b['threshold']}: "
                     f"{'MET' if b['meets_threshold'] else 'MISSED'}]")
        print(line)
    ps = report["pii_scan"]
    print(f"  pii scan: {ps['payloads_scanned']} payloads, {ps['leaks']} leaks"
          + ("" if report["pii_masking"] else " (gate OFF: leaks expected)"))


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("systems", nargs="*", choices=list(SYSTEMS), default=[],
                        help="which systems to run (default: all)")
    args = parser.parse_args()
    systems = args.systems or list(SYSTEMS)

    RESULTS_DIR.mkdir(exist_ok=True)
    try:
        for system in systems:
            report = await run_system(system)
            out = RESULTS_DIR / f"{system}.json"
            out.write_text(json.dumps(report, indent=2, default=str) + "\n")
            _print_summary(report)
            print(f"  written to {out}")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
