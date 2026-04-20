"""PostgreSQL repository placeholders.

This module intentionally keeps the shape of the future implementation small.
Next phase should add:

- SQLAlchemy engine/session factory
- ORM models mapped to db/schema.sql
- repository methods matching the in-memory store API
- transaction boundaries for run + run_steps + run_events
"""


class PostgresStore:
    """Placeholder shape for the future PostgreSQL implementation."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
