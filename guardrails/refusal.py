"""Refusal guard: a specificity filter, not a topic filter.

General principles applied to the user's numbers = education (allowed).
Product-level recommendations ("should I buy X fund?") = refused
(SEBI RIA regulation in India).

Lives in each approach's prompt/loop rather than as a hard pre-router, so the
refusal rate is a measured property of each system in the eval matrix.
This module holds the shared refusal criteria text and the refusal detector
used by the eval harness.
"""
