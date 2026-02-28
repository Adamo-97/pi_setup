# -*- coding: utf-8 -*-
"""
Database Connection Manager
=============================
Provides a thread-safe, context-managed PostgreSQL connection pool
using psycopg2. All database operations should use this module
to get connections.

Usage:
    from database.connection import get_connection, get_pool

    # Option 1: Context manager (auto-commits on success, rolls back on error)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")

    # Option 2: Get pool for advanced use
    pool = get_pool()
"""

import logging
import sys
from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2.extras import RealDictCursor

# ---------------------------------------------------------------------------
# Logger — writes to stderr so stdout stays clean for JSON output
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level connection pool (singleton)
# ---------------------------------------------------------------------------
_connection_pool: pg_pool.ThreadedConnectionPool | None = None


def init_pool(
    dsn: str, min_conn: int = 2, max_conn: int = 10
) -> pg_pool.ThreadedConnectionPool:
    """
    Initialize the global connection pool.
    Called once at application startup.

    Args:
        dsn: PostgreSQL connection string (from DatabaseConfig.connection_string).
        min_conn: Minimum connections to keep open.
        max_conn: Maximum connections allowed.

    Returns:
        The initialized ThreadedConnectionPool.
    """
    global _connection_pool

    if _connection_pool is not None:
        logger.warning("Connection pool already initialized — returning existing pool.")
        return _connection_pool

    try:
        _connection_pool = pg_pool.ThreadedConnectionPool(
            minconn=min_conn,
            maxconn=max_conn,
            dsn=dsn,
        )
        logger.info(
            "PostgreSQL connection pool initialized (min=%d, max=%d).",
            min_conn,
            max_conn,
        )
        return _connection_pool

    except psycopg2.Error as exc:
        logger.critical("Failed to initialize PostgreSQL pool: %s", exc)
        sys.exit(1)


def get_pool() -> pg_pool.ThreadedConnectionPool:
    """Return the global connection pool, initializing from settings if needed."""
    global _connection_pool

    if _connection_pool is None:
        # Late import to avoid circular dependency with config
        from config.settings import settings

        init_pool(settings.database.connection_string)

    return _connection_pool


@contextmanager
def get_connection(dict_cursor: bool = True) -> Generator:
    """
    Context manager that checks out a connection from the pool,
    yields it, and returns it when done.

    - Auto-commits on successful exit.
    - Rolls back on exception, then re-raises.

    Args:
        dict_cursor: If True, cursors return dicts instead of tuples.

    Yields:
        A psycopg2 connection object.
    """
    _pool = get_pool()
    conn = _pool.getconn()

    try:
        # Set default cursor factory for this connection
        if dict_cursor:
            conn.cursor_factory = RealDictCursor

        yield conn
        conn.commit()

    except Exception:
        conn.rollback()
        logger.exception("Database operation failed — transaction rolled back.")
        raise

    finally:
        _pool.putconn(conn)


def close_pool() -> None:
    """Cleanly close all connections in the pool. Call on shutdown."""
    global _connection_pool

    if _connection_pool is not None:
        _connection_pool.closeall()
        _connection_pool = None
        logger.info("PostgreSQL connection pool closed.")


def execute_query(
    query: str,
    params: tuple | None = None,
    fetch: bool = True,
) -> list[dict] | None:
    """
    Execute a single query and optionally fetch results.

    Args:
        query: SQL query string with %s placeholders.
        params: Tuple of parameters for the query.
        fetch: If True, return all rows as list of dicts.

    Returns:
        List of dicts if fetch=True, else None.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)

            if fetch:
                return cur.fetchall()
            return None


def execute_many(query: str, params_list: list[tuple]) -> None:
    """
    Execute a query many times with different parameter sets.
    Uses executemany for batch operations.

    Args:
        query: SQL query string with %s placeholders.
        params_list: List of parameter tuples.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(query, params_list)
            logger.info("Batch execute: %d rows affected.", cur.rowcount)
