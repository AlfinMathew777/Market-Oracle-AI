"""db — PostgreSQL connection layer for Market Oracle AI.

Provides a drop-in-compatible replacement for aiosqlite's async context-manager
interface, enabling database.py to branch on DATABASE_URL without rewriting any
SQL query logic.

Usage:
    from db import get_pg_db, init_pg_pool, close_pg_pool
"""

from db.connection import get_pg_db, init_pg_pool, close_pg_pool

__all__ = ["get_pg_db", "init_pg_pool", "close_pg_pool"]
