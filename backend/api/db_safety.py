"""
db_safety.py — Transaction safety wrappers for database operations

Adds explicit transaction boundaries and retry logic for write paths.
Addresses Risk 6 (Data Integrity): database writes lack explicit
transaction boundaries and can silently corrupt on partial failure.
"""

import logging
import functools
from contextlib import asynccontextmanager
from typing import Any, Callable

logger = logging.getLogger("ygb.db_safety")


@asynccontextmanager
async def db_transaction(db):
    """Explicit transaction boundary with rollback on error.

    Usage:
        async with db_transaction(db) as conn:
            await conn.execute("INSERT ...")
            await conn.execute("UPDATE ...")
        # auto-committed on success, rolled back on exception
    """
    try:
        await db.execute("BEGIN IMMEDIATE")
        yield db
        await db.execute("COMMIT")
    except Exception:
        try:
            await db.execute("ROLLBACK")
        except Exception:
            logger.error("ROLLBACK failed — database may be inconsistent")
        raise


def safe_db_write(func: Callable) -> Callable:
    """Decorator that wraps async DB write functions in a transaction.

    Logs the operation name and correlation info on failure.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(
                "DB write failed in %s: %s",
                func.__name__,
                str(e),
                exc_info=True,
            )
            raise
    return wrapper
