"""Apply db/schema.sql to the configured database. The schema is fully
idempotent (IF NOT EXISTS everywhere), so re-running after edits is safe;
shape changes to existing tables are handled by drop + re-seed instead of
migrations (recorded decision: Alembic rejected for a re-seedable synthetic DB).

Blocked on db/schema.sql approval.
"""
