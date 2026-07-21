"""LLM-as-judge for the buckets deterministic scoring cannot settle:
education (are the rubric points actually covered, correctly?) and composite
(did the answer synthesize the user's real numbers with the concept?).

Judge/actor separation is prompt-level, not model-family-level: the cohort
key grants no stronger model than gpt-5.4-mini (README Failure Analysis
entry 9), so the judge runs the same model with a separate, adversarial
prompt, sees only the question, the answer, and the rubric (never the
actor's tools or retrieval), and returns strict JSON at temperature 0.

Verdicts: education passed = judge pass. Composite passed = judge pass;
the deterministic component_recall stays recorded alongside as evidence.

Reads eval/results/<system>.json (written by run_eval), fills in passed for
every pending_judge entry, recomputes the summary, writes the file back.
Idempotent: nothing is re-judged unless --rejudge is given.

Usage:
    python -m eval.judge                 # judge every results file present
    python -m eval.judge rag [--rejudge]
"""

import argparse
import asyncio
import json

from app.config import settings
from eval.run_eval import RESULTS_DIR, SYSTEMS, load_golden, summarize

JUDGE_SYSTEM_PROMPT = """\
You are a strict, skeptical evaluation judge for a personal-finance Q&A \
system built for a user in India. You are given one question, the system's \
answer, and a rubric. Judge ONLY against the rubric; do not reward style, \
length, or extra content.

pass = true only if the answer conveys the substance of EVERY rubric point \
(wording may differ), contains nothing that contradicts a rubric point, and \
actually answers the question asked.

Return JSON exactly in this shape:
{"pass": true or false, "missing": ["rubric points not adequately covered"],
 "reason": "one or two sentences"}"""


def _rubric(question: dict) -> list[str]:
    return question.get("expected_points") or question.get("expected_concepts")


async def judge_one(client, question: dict, answer: str) -> dict:
    rubric_lines = "\n".join(f"- {p}" for p in _rubric(question))
    user_prompt = (
        f"Question:\n{question['question']}\n\n"
        f"System's answer:\n{answer}\n\n"
        f"Rubric (every point must be covered):\n{rubric_lines}"
    )
    response = await client.chat.completions.create(
        model=settings.judge_model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                  {"role": "user", "content": user_prompt}],
    )
    verdict = json.loads(response.choices[0].message.content)
    return {"pass": bool(verdict.get("pass")),
            "missing": verdict.get("missing", []),
            "reason": verdict.get("reason", "")}


async def judge_file(system: str, client, rejudge: bool = False,
                     suffix: str = "") -> dict:
    """Judge one results file in place. Returns the updated report."""
    path = RESULTS_DIR / f"{system}{suffix}.json"
    report = json.loads(path.read_text())
    _, questions, _ = load_golden()
    by_id = {q["id"]: q for q in questions}

    judged = 0
    for entry in report["results"]:
        if entry.get("error"):
            continue  # already a hard fail; nothing to judge
        if not rejudge and not entry.get("pending_judge"):
            continue
        question = by_id[entry["id"]]
        if _rubric(question) is None:
            continue
        verdict = await judge_one(client, question, entry["answer"])
        entry["passed"] = verdict["pass"]
        entry["judge"] = verdict
        entry["pending_judge"] = False
        judged += 1

    report["summary"] = summarize(report["results"])
    report["judge_model"] = settings.judge_model
    path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    return {"system": system, "judged": judged, "summary": report["summary"]}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    # no argparse choices= here: with nargs="*" it rejects the empty default
    parser.add_argument("systems", nargs="*", default=[])
    parser.add_argument("--rejudge", action="store_true",
                        help="re-judge entries that already have a verdict")
    parser.add_argument("--tag", default="",
                        help="suffix matching the run_eval --tag to judge")
    args = parser.parse_args()
    suffix = f"_{args.tag}" if args.tag else ""
    unknown = set(args.systems) - set(SYSTEMS)
    if unknown:
        raise SystemExit(f"unknown systems {sorted(unknown)}; valid: {list(SYSTEMS)}")
    systems = args.systems or [s for s in SYSTEMS
                               if (RESULTS_DIR / f"{s}{suffix}.json").exists()]
    if not systems:
        raise SystemExit("no results files found; run eval.run_eval first")
    if not settings.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is empty in .env")

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    print(f"judge model: {settings.judge_model}"
          + (f"  |  reading *{suffix}.json" if suffix else ""))

    for system in systems:
        outcome = await judge_file(system, client, rejudge=args.rejudge,
                                   suffix=suffix)
        print(f"{system}: judged {outcome['judged']} answers")
        for bucket in ("education", "composite"):
            b = outcome["summary"].get(bucket)
            if b:
                print(f"  {bucket:10s} {b['passed']}/{b['n']} passed "
                      f"({b['pending_judge']} still pending)")


if __name__ == "__main__":
    asyncio.run(main())
