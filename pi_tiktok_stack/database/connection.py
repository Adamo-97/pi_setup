# -*- coding: utf-8 -*-
"""
Database Connection Pool
========================
Thread-safe PostgreSQL connection pool with context-manager support.
"""

import logging
import sys
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import settings

logger = logging.getLogger("tiktok.db")

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        cfg = settings.database
        _pool = pool.ThreadedConnectionPool(
            minconn=cfg.min_connections,
            maxconn=cfg.max_connections,
            host=cfg.host,
            port=cfg.port,
            dbname=cfg.name,
            user=cfg.user,
            password=cfg.password,
        )
        logger.info("Connection pool created (%s:%s/%s)", cfg.host, cfg.port, cfg.name)
    return _pool


@contextmanager
def get_connection():
    """Yield a connection from the pool; auto-commit on success, rollback on error."""
    p = _get_pool()
    conn = p.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)


def execute_query(sql, params=None, fetch=True):
    """Run a query and return rows (list[dict]) or None."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            if fetch and cur.description:
                return [dict(r) for r in cur.fetchall()]
            return None


def execute_many(sql, params_list):
    """Execute a query for each set of params."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, params_list)


def close_pool():
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("Connection pool closed.")
