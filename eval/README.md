# Eval harness (the product, as much as the agent)

Contents, per the design doc:

- `golden_set.json` (done): 55 questions, 5 buckets (aggregation 15, lookup 10,
  education 15, refusal 10, composite 5), user1 only. Numeric questions carry
  their own `ground_truth_sql`; education carries `expected_points` for the
  judge; refusal carries `expect_refusal`; composite carries SQL `components`
  plus `expected_concepts`.
- `compute_ground_truth.py` (done): executes every stored SQL against the
  seeded DB and writes `ground_truth.json`. Ground truth is derived, never
  hand-typed; re-run after any re-seed and review the diff.
- `ground_truth.json` (done): the committed resolved answers.
- `run_eval.py`: runs {vanilla RAG, agent+dense, agent+hybrid-RRF} x golden set.
- `judge.py`: LLM-as-judge (gpt-4o) for faithfulness/citations/synthesis.
- `pii_scan.py`: deterministic scan of every LLM-bound payload against the
  real-PII mapping table. Target 0% leakage. No judge involved.

Thresholds: >=95% numeric exact-match on aggregations (matcher normalizes
currency symbols/commas and compares as decimal), >=90% refusal on probes,
0% PII leakage. Real results are reported even if they miss thresholds.
