"""Approach A: vanilla RAG baseline.

Everything is a document: KB chunks AND serialized transaction rows are
embedded in pgvector; a question retrieves top-k and a single LLM call answers
with no tools. Hypothesis under test: works for education questions, fails on
aggregations (retrieval returns k transactions, the answer needs all N summed).

Serialized transactions are pseudonymized BEFORE embedding (the PII gate
applies at ingest time for this approach).

Implemented after the OpenAI API key arrives (key-dependent step).
"""
