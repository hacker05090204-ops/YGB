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
_TX_FLAG = "_ygb_tx_active"


@asynccontextmanager
async def db_transaction(db):
    """Explicit transaction boundary with rollback on error.

    Usage:
        async with db_transaction(db) as conn:
            await conn.execute("INSERT ...")
            await conn.execute("UPDATE ...")
        # auto-committed on success, rolled back on exception
    """
    nested = bool(getattr(db, _TX_FLAG, False))
    if nested:
        yield db
        return

    try:
        setattr(db, _TX_FLAG, True)
    except Exception as exc:
        logger.debug("Failed to mark DB transaction state as active: %s", exc, exc_info=True)

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
    finally:
        try:
            setattr(db, _TX_FLAG, False)
        except Exception as exc:
            logger.debug("Failed to clear DB transaction state: %s", exc, exc_info=True)


def _resolve_db_handle(args: tuple, kwargs: dict) -> Any:
    """Best-effort DB handle lookup for transaction-wrapping decorators."""
    db = kwargs.get("db")
    if hasattr(db, "execute"):
        return db

    for arg in args:
        if hasattr(arg, "execute"):
            return arg

        for attr in ("db", "_db", "conn", "_conn"):
            candidate = getattr(arg, attr, None)
            if hasattr(candidate, "execute"):
                return candidate

    return None


def safe_db_write(func: Callable) -> Callable:
    """Decorator that wraps async DB write functions in a transaction.

    Logs the operation name and correlation info on failure.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        db = _resolve_db_handle(args, kwargs)
        try:
            if db is None or getattr(db, _TX_FLAG, False):
                return await func(*args, **kwargs)

            async with db_transaction(db):
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
