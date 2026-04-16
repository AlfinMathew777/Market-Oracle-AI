"""Migration runner for Market Oracle AI PostgreSQL schema.

Usage:
    python -m migrations.run_migrations

Or from server.py lifespan when DATABASE_URL is set.

Runs each migration SQL file in `migrations/` exactly once, tracked in the
`schema_migrations` table. Safe to call on every startup — already-applied
migrations are skipped.
"""

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent


async def run_migrations(dsn: str) -> None:
    """Apply all pending SQL migrations to the PostgreSQL database."""
    try:
        import asyncpg
    except ImportError:
        logger.error("asyncpg not installed — cannot run PG migrations. pip install asyncpg")
        raise

    conn = await asyncpg.connect(dsn)
    try:
        # Ensure schema_migrations table exists (bootstraps itself)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # Collect applied versions
        rows = await conn.fetch("SELECT version FROM schema_migrations ORDER BY version")
        applied = {r["version"] for r in rows}

        # Discover migration files, sorted by filename
        migration_files = sorted(
            f for f in _MIGRATIONS_DIR.glob("*.sql")
            if f.stem not in applied
        )

        if not migration_files:
            logger.info("No pending migrations — database is up to date")
            return

        for mf in migration_files:
            version = mf.stem
            logger.info("Applying migration: %s", version)
            sql = mf.read_text(encoding="utf-8")

            async with conn.transaction():
                # asyncpg executes the entire script as one transaction
                # Split on semicolons to handle partial-index WHERE clauses safely
                statements = [s.strip() for s in sql.split(";") if s.strip()]
                for stmt in statements:
                    try:
                        await conn.execute(stmt)
                    except Exception as exc:
                        msg = str(exc).lower()
                        if "already exists" in msg or "duplicate" in msg:
                            logger.debug("Migration %s: skipping existing — %s", version, exc)
                        else:
                            logger.error(
                                "Migration %s failed on statement:\n%s\nError: %s",
                                version, stmt[:200], exc,
                            )
                            raise

            logger.info("Migration %s applied successfully", version)

    finally:
        await conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL environment variable not set")
        raise SystemExit(1)
    asyncio.run(run_migrations(dsn))
