# Eval harness (the product, as much as the agent)

Planned contents, per the design doc:

- `golden_set.json`: ~55 questions, 5 buckets (aggregation 15, lookup 10,
  education 15, refusal 10, composite 5), user1 only.
- `ground_truth.py`: precomputes numeric answers via SQL against the seeded DB.
- `run_eval.py`: runs {vanilla RAG, agent+dense, agent+hybrid-RRF} x golden set.
- `judge.py`: LLM-as-judge (gpt-4o) for faithfulness/citations/synthesis.
- `pii_scan.py`: deterministic scan of every LLM-bound payload against the
  real-PII mapping table. Target 0% leakage. No judge involved.

Thresholds: >=95% numeric exact-match on aggregations (matcher normalizes
currency symbols/commas and compares as decimal), >=90% refusal on probes,
0% PII leakage. Real results are reported even if they miss thresholds.
