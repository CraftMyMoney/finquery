"""Forward pseudonymization: real PII -> consistent fake values.

Applied at every LLM boundary in BOTH approaches:
  - tool outputs before they enter agent context (approach B)
  - serialized transactions before embedding (approach A)
  - user questions before they reach the LLM

Detection = regex (account numbers, phone numbers, UPI VPAs, card fragments)
+ known-values list from the per-user pii_mappings table. Free-text name NER
is documented out of scope. Reverse mapping is an optional extension.

Pure functions + mapping table, no LLM involved. Key-independent: implemented
next with unit tests in tests/test_pii.py.
"""
