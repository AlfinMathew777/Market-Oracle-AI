"""PostgreSQL async connection wrapper for Market Oracle AI.

Provides aiosqlite-compatible API so database.py can transparently switch
between SQLite (local dev, no DATABASE_URL) and PostgreSQL (staging/prod).

Key compatibility points implemented:
  - get_pg_db() returns an async context manager yielding PgConnection
  - PgConnection.execute(sql, params) returns _PgExecuteContextManager which
    is BOTH awaitable (for INSERT/UPDATE/DELETE) AND an async context manager
    (for SELECT with cursor iteration)
  - PgConnection.row_factory attribute — set to dict-returning lambda to match
    aiosqlite convention; PgConnection respects it automatically (asyncpg
    returns Record objects; we convert to dict when row_factory is set)
  - PgConnection.executescript(sql) — runs multiple statements in a transaction
  - cursor.fetchone(), cursor.fetchall(), cursor.lastrowid, cursor.rowcount
  - ? placeholder translation → $1, $2, … (asyncpg uses numbered placeholders)
  - INSERT … OR REPLACE → INSERT … ON CONFLICT DO UPDATE SET (auto-rewrite)
  - db.commit() — no-op (asyncpg auto-commits; explicit transactions via
    pool.transaction() are handled at query level)
"""

import re
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional, Sequence

logger = logging.getLogger(__name__)

# Module-level asyncpg pool — initialised once by init_pg_pool()
_pool = None


async def init_pg_pool(dsn: str, min_size: int = 2, max_size: int = 10) -> None:
    """Create the asyncpg connection pool. Call once at application startup."""
    global _pool
    if _pool is not None:
        return
    try:
        import asyncpg
        _pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
        logger.info("PostgreSQL pool created (min=%d, max=%d)", min_size, max_size)
    except Exception as exc:
        logger.error("Failed to create PostgreSQL pool: %s", exc)
        raise


async def close_pg_pool() -> None:
    """Gracefully close the connection pool. Call on application shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL pool closed")


def _to_pg_placeholders(sql: str) -> str:
    """Replace ? positional placeholders with $1, $2, … for asyncpg."""
    count = 0

    def replacer(_match: re.Match) -> str:
        nonlocal count
        count += 1
        return f"${count}"

    return re.sub(r"\?", replacer, sql)


def _rewrite_insert_or_replace(sql: str) -> str:
    """
    Translate SQLite's INSERT OR REPLACE … into PostgreSQL's
    INSERT … ON CONFLICT DO UPDATE SET … idiom.

    This is a best-effort rewrite that handles the patterns used in database.py.
    It extracts the table name, column list, and VALUES clause, then appends
    an ON CONFLICT clause that updates every non-PK column.

    If the SQL does not start with INSERT OR REPLACE this function is a no-op.
    """
    stripped = sql.strip()
    if not re.match(r"(?i)INSERT\s+OR\s+REPLACE", stripped):
        return sql

    # Swap INSERT OR REPLACE → INSERT
    rewritten = re.sub(r"(?i)INSERT\s+OR\s+REPLACE", "INSERT", stripped, count=1)

    # Extract table and column list: INSERT INTO table (col1, col2, …) VALUES …
    m = re.search(
        r"(?i)INSERT\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES",
        rewritten,
    )
    if not m:
        # Cannot parse — fall back to plain INSERT (will raise on conflict)
        logger.warning("Could not parse INSERT OR REPLACE for PG rewrite; using plain INSERT")
        return rewritten

    table = m.group(1)
    cols = [c.strip() for c in m.group(2).split(",")]

    # Determine the primary key column — first column by convention in our schema
    pk_col = cols[0]
    update_pairs = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in cols if c != pk_col
    )

    on_conflict = f" ON CONFLICT ({pk_col}) DO UPDATE SET {update_pairs}"
    return rewritten + on_conflict


def _append_returning_id(sql: str) -> str:
    """Append RETURNING id to INSERT statements that don't already have it."""
    stripped = sql.strip().rstrip(";")
    if re.match(r"(?i)INSERT", stripped) and "RETURNING" not in stripped.upper():
        return stripped + " RETURNING id"
    return stripped


class _PgCursor:
    """
    Minimal cursor object returned by _PgExecuteContextManager.
    Exposes fetchone(), fetchall(), lastrowid, rowcount — matching aiosqlite.
    """

    def __init__(
        self,
        rows: list,
        rowcount: int,
        lastrowid: Optional[Any],
        row_factory=None,
    ):
        self._rows = rows
        self.rowcount = rowcount
        self.lastrowid = lastrowid
        self._row_factory = row_factory
        self._pos = 0

    def _apply_factory(self, row):
        if self._row_factory is None or row is None:
            return row
        # aiosqlite row_factory: lambda cursor, row → dict
        # asyncpg returns Record — convert to plain tuple for compatibility
        return self._row_factory(self, tuple(row))

    async def fetchone(self):
        if not self._rows:
            return None
        row = self._rows[0]
        return self._apply_factory(row)

    async def fetchall(self):
        return [self._apply_factory(r) for r in self._rows]

    # Iteration support (rare but used in tests)
    def __aiter__(self):
        self._pos = 0
        return self

    async def __anext__(self):
        if self._pos >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._pos]
        self._pos += 1
        return self._apply_factory(row)


class _PgExecuteContextManager:
    """
    Returned by PgConnection.execute(). Supports two usage patterns:

      # Pattern 1 — awaitable (INSERT / UPDATE / DELETE)
      cur = await db.execute(sql, params)
      print(cur.rowcount)

      # Pattern 2 — async context manager (SELECT)
      async with db.execute(sql, params) as cur:
          rows = await cur.fetchall()
    """

    def __init__(self, conn, sql: str, params: Sequence, row_factory=None):
        self._conn = conn
        self._sql = sql
        self._params = params
        self._row_factory = row_factory
        self._cursor: Optional[_PgCursor] = None

    async def _execute(self) -> _PgCursor:
        if self._cursor is not None:
            return self._cursor

        sql = _rewrite_insert_or_replace(self._sql)
        is_insert = re.match(r"(?i)\s*INSERT", sql)
        if is_insert:
            sql = _append_returning_id(sql)
        sql = _to_pg_placeholders(sql)

        # Convert params — asyncpg does not accept None in lists for some types;
        # coerce empty sequences gracefully.
        params = list(self._params) if self._params else []

        try:
            rows: list = []
            rowcount = 0
            lastrowid = None

            if re.match(r"(?i)\s*(SELECT|WITH)", sql):
                raw_rows = await self._conn.fetch(sql, *params)
                rows = [tuple(r) for r in raw_rows]
                rowcount = len(rows)
            elif is_insert:
                row = await self._conn.fetchrow(sql, *params)
                if row:
                    lastrowid = row.get("id")
                rowcount = 1
            else:
                status = await self._conn.execute(sql, *params)
                # asyncpg returns e.g. "UPDATE 3" or "DELETE 1"
                parts = status.split()
                if len(parts) >= 2 and parts[-1].isdigit():
                    rowcount = int(parts[-1])

            self._cursor = _PgCursor(rows, rowcount, lastrowid, self._row_factory)
        except Exception as exc:
            logger.error("PG execute failed — SQL: %.200s | error: %s", sql, exc)
            raise

        return self._cursor

    # Awaitable — used for INSERT/UPDATE/DELETE
    def __await__(self):
        return self._execute().__await__()

    # Async context manager — used for SELECT
    async def __aenter__(self) -> _PgCursor:
        return await self._execute()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False  # Do not suppress exceptions


class PgConnection:
    """
    Wraps an asyncpg connection to provide the aiosqlite Connection interface
    expected by database.py.
    """

    def __init__(self, raw_conn):
        self._conn = raw_conn
        self.row_factory = None  # Set by callers: lambda c, r: dict(zip(...))

    def execute(self, sql: str, params: Sequence = ()) -> _PgExecuteContextManager:
        """Return an object that is both awaitable and an async context manager."""
        return _PgExecuteContextManager(self._conn, sql, params, self.row_factory)

    async def executescript(self, script: str) -> None:
        """Run a multi-statement SQL script in a single transaction."""
        # Split on semicolons, filter blanks, execute sequentially
        statements = [s.strip() for s in script.split(";") if s.strip()]
        async with self._conn.transaction():
            for stmt in statements:
                # Skip SQLite-only constructs
                if "WHERE actual_direction IS NULL" in stmt and "CREATE INDEX" in stmt:
                    # Partial index — supported in PG, keep as-is
                    pass
                translated = _to_pg_placeholders(stmt)
                try:
                    await self._conn.execute(translated)
                except Exception as exc:
                    # Tolerate "already exists" errors (idempotent schema)
                    msg = str(exc).lower()
                    if "already exists" in msg or "duplicate" in msg:
                        logger.debug("Skipping existing object: %.80s", exc)
                    else:
                        raise

    async def commit(self) -> None:
        """No-op — asyncpg auto-commits outside explicit transactions."""

    async def close(self) -> None:
        await self._conn.close()


@asynccontextmanager
async def get_pg_db():
    """
    Async context manager yielding a PgConnection.

    Usage:
        async with get_pg_db() as db:
            async with db.execute("SELECT 1") as cur:
                row = await cur.fetchone()
    """
    if _pool is None:
        raise RuntimeError(
            "PostgreSQL pool not initialised — call init_pg_pool() at startup"
        )
    async with _pool.acquire() as raw_conn:
        yield PgConnection(raw_conn)
