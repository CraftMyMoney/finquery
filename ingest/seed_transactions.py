"""Load fake-data/*.csv into Postgres (users, transactions, budgets) and build
the per-user pii_mappings table from the known fake identities. Idempotent:
truncate-and-reload, since all data is synthetic and regenerable.

Blocked on db/schema.sql approval.
"""
