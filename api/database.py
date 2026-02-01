"""
YGB Database Module

PostgreSQL database connection and operations for the YGB Bug Bounty System.
Uses asyncpg for async database operations with Neon PostgreSQL.
"""

import asyncpg
import os
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any
import uuid

# Database URL from environment or direct connection
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_x3OP8cCHBwdE@ep-hidden-leaf-ahzn6hmu-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"
)

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def init_database():
    """Initialize database tables."""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        # Create users table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE,
                role VARCHAR(50) DEFAULT 'researcher',
                avatar_url TEXT,
                total_bounties INTEGER DEFAULT 0,
                total_earnings DECIMAL(12, 2) DEFAULT 0.00,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                last_active TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        # Create targets table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS targets (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                program_name VARCHAR(255) NOT NULL,
                scope TEXT NOT NULL,
                link TEXT,
                platform VARCHAR(100),
                payout_tier VARCHAR(50) DEFAULT 'MEDIUM',
                status VARCHAR(50) DEFAULT 'ACTIVE',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        # Create bounties table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bounties (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                target_id UUID REFERENCES targets(id) ON DELETE SET NULL,
                title VARCHAR(500) NOT NULL,
                description TEXT,
                severity VARCHAR(50) DEFAULT 'MEDIUM',
                status VARCHAR(50) DEFAULT 'PENDING',
                reward DECIMAL(12, 2) DEFAULT 0.00,
                submitted_at TIMESTAMPTZ DEFAULT NOW(),
                resolved_at TIMESTAMPTZ
            )
        """)
        
        # Create sessions table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                mode VARCHAR(50) DEFAULT 'MOCK',
                target_scope TEXT,
                progress INTEGER DEFAULT 0,
                status VARCHAR(50) DEFAULT 'ACTIVE',
                started_at TIMESTAMPTZ DEFAULT NOW(),
                ended_at TIMESTAMPTZ
            )
        """)
        
        # Create activity_log table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                action_type VARCHAR(100) NOT NULL,
                description TEXT,
                metadata JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
    print("✅ Database tables initialized")


# =============================================================================
# USER OPERATIONS
# =============================================================================

async def create_user(name: str, email: str = None, role: str = "researcher") -> Dict[str, Any]:
    """Create a new user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO users (name, email, role)
            VALUES ($1, $2, $3)
            RETURNING id, name, email, role, total_bounties, total_earnings, created_at
        """, name, email, role)
        return dict(row)


async def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Get a user by ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, name, email, role, avatar_url, total_bounties, total_earnings, created_at, last_active
            FROM users WHERE id = $1
        """, uuid.UUID(user_id))
        return dict(row) if row else None


async def get_all_users() -> List[Dict[str, Any]]:
    """Get all users."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, name, email, role, avatar_url, total_bounties, total_earnings, created_at, last_active
            FROM users ORDER BY created_at DESC
        """)
        return [dict(row) for row in rows]


async def update_user_stats(user_id: str, bounties: int = None, earnings: float = None):
    """Update user statistics."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if bounties is not None:
            await conn.execute("UPDATE users SET total_bounties = $1 WHERE id = $2", bounties, uuid.UUID(user_id))
        if earnings is not None:
            await conn.execute("UPDATE users SET total_earnings = $1 WHERE id = $2", earnings, uuid.UUID(user_id))
        await conn.execute("UPDATE users SET last_active = NOW() WHERE id = $1", uuid.UUID(user_id))


# =============================================================================
# TARGET OPERATIONS
# =============================================================================

async def create_target(program_name: str, scope: str, link: str = None, 
                        platform: str = None, payout_tier: str = "MEDIUM") -> Dict[str, Any]:
    """Create a new target."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO targets (program_name, scope, link, platform, payout_tier)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, program_name, scope, link, platform, payout_tier, status, created_at
        """, program_name, scope, link, platform, payout_tier)
        return dict(row)


async def get_all_targets() -> List[Dict[str, Any]]:
    """Get all targets."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, program_name, scope, link, platform, payout_tier, status, created_at
            FROM targets ORDER BY created_at DESC
        """)
        return [dict(row) for row in rows]


async def get_target(target_id: str) -> Optional[Dict[str, Any]]:
    """Get a target by ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, program_name, scope, link, platform, payout_tier, status, created_at
            FROM targets WHERE id = $1
        """, uuid.UUID(target_id))
        return dict(row) if row else None


# =============================================================================
# BOUNTY OPERATIONS
# =============================================================================

async def create_bounty(user_id: str, target_id: str, title: str, 
                        description: str = None, severity: str = "MEDIUM") -> Dict[str, Any]:
    """Create a new bounty submission."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO bounties (user_id, target_id, title, description, severity)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, user_id, target_id, title, description, severity, status, reward, submitted_at
        """, uuid.UUID(user_id), uuid.UUID(target_id) if target_id else None, title, description, severity)
        
        # Update user bounty count
        await conn.execute("""
            UPDATE users SET total_bounties = total_bounties + 1 WHERE id = $1
        """, uuid.UUID(user_id))
        
        return dict(row)


async def get_user_bounties(user_id: str) -> List[Dict[str, Any]]:
    """Get all bounties for a user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT b.id, b.title, b.description, b.severity, b.status, b.reward, b.submitted_at,
                   t.program_name, t.scope, t.link
            FROM bounties b
            LEFT JOIN targets t ON b.target_id = t.id
            WHERE b.user_id = $1
            ORDER BY b.submitted_at DESC
        """, uuid.UUID(user_id))
        return [dict(row) for row in rows]


async def get_all_bounties() -> List[Dict[str, Any]]:
    """Get all bounties with user and target info."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT b.id, b.title, b.severity, b.status, b.reward, b.submitted_at,
                   u.name as user_name, u.email as user_email,
                   t.program_name, t.scope
            FROM bounties b
            LEFT JOIN users u ON b.user_id = u.id
            LEFT JOIN targets t ON b.target_id = t.id
            ORDER BY b.submitted_at DESC
        """)
        return [dict(row) for row in rows]


async def update_bounty_status(bounty_id: str, status: str, reward: float = None):
    """Update bounty status and reward."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if reward is not None:
            await conn.execute("""
                UPDATE bounties 
                SET status = $1, reward = $2, resolved_at = NOW()
                WHERE id = $3
            """, status, reward, uuid.UUID(bounty_id))
            
            # Update user earnings
            row = await conn.fetchrow("SELECT user_id FROM bounties WHERE id = $1", uuid.UUID(bounty_id))
            if row:
                await conn.execute("""
                    UPDATE users SET total_earnings = total_earnings + $1 WHERE id = $2
                """, reward, row['user_id'])
        else:
            await conn.execute("""
                UPDATE bounties SET status = $1 WHERE id = $2
            """, status, uuid.UUID(bounty_id))


# =============================================================================
# SESSION OPERATIONS
# =============================================================================

async def create_session(user_id: str, mode: str, target_scope: str = None) -> Dict[str, Any]:
    """Create a new session."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO sessions (user_id, mode, target_scope)
            VALUES ($1, $2, $3)
            RETURNING id, user_id, mode, target_scope, progress, status, started_at
        """, uuid.UUID(user_id), mode, target_scope)
        return dict(row)


async def get_user_sessions(user_id: str) -> List[Dict[str, Any]]:
    """Get all sessions for a user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, mode, target_scope, progress, status, started_at, ended_at
            FROM sessions WHERE user_id = $1
            ORDER BY started_at DESC
        """, uuid.UUID(user_id))
        return [dict(row) for row in rows]


async def update_session_progress(session_id: str, progress: int, status: str = None):
    """Update session progress."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if status:
            await conn.execute("""
                UPDATE sessions SET progress = $1, status = $2, ended_at = CASE WHEN $2 = 'COMPLETED' THEN NOW() ELSE ended_at END
                WHERE id = $3
            """, progress, status, uuid.UUID(session_id))
        else:
            await conn.execute("UPDATE sessions SET progress = $1 WHERE id = $2", progress, uuid.UUID(session_id))


# =============================================================================
# ACTIVITY LOG
# =============================================================================

async def log_activity(user_id: str, action_type: str, description: str = None, metadata: dict = None):
    """Log user activity."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO activity_log (user_id, action_type, description, metadata)
            VALUES ($1, $2, $3, $4)
        """, uuid.UUID(user_id) if user_id else None, action_type, description, 
           metadata if metadata else None)


async def get_recent_activity(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent activity log."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT a.id, a.action_type, a.description, a.created_at,
                   u.name as user_name
            FROM activity_log a
            LEFT JOIN users u ON a.user_id = u.id
            ORDER BY a.created_at DESC
            LIMIT $1
        """, limit)
        return [dict(row) for row in rows]


# =============================================================================
# ADMIN STATS
# =============================================================================

async def get_admin_stats() -> Dict[str, Any]:
    """Get admin dashboard statistics."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # User stats
        user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        active_users = await conn.fetchval("""
            SELECT COUNT(*) FROM users WHERE last_active > NOW() - INTERVAL '7 days'
        """)
        
        # Bounty stats
        total_bounties = await conn.fetchval("SELECT COUNT(*) FROM bounties")
        pending_bounties = await conn.fetchval("SELECT COUNT(*) FROM bounties WHERE status = 'PENDING'")
        total_paid = await conn.fetchval("SELECT COALESCE(SUM(reward), 0) FROM bounties WHERE status = 'PAID'")
        
        # Target stats
        target_count = await conn.fetchval("SELECT COUNT(*) FROM targets")
        active_targets = await conn.fetchval("SELECT COUNT(*) FROM targets WHERE status = 'ACTIVE'")
        
        # Session stats
        active_sessions = await conn.fetchval("SELECT COUNT(*) FROM sessions WHERE status = 'ACTIVE'")
        
        return {
            "users": {
                "total": user_count,
                "active_last_7_days": active_users
            },
            "bounties": {
                "total": total_bounties,
                "pending": pending_bounties,
                "total_paid": float(total_paid or 0)
            },
            "targets": {
                "total": target_count,
                "active": active_targets
            },
            "sessions": {
                "active": active_sessions
            }
        }
