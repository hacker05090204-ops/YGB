"""Migration script from JSON-file storage to SQLite database.

This script migrates all existing data from the JSON-file storage format
to the new SQLite database format, preserving all data and relationships.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.database import init_database as init_json, close_pool as close_json
from api.database_sqlite import get_db, Database


async def migrate_data():
    """Migrate all data from JSON files to SQLite."""

    # Initialize connections
    await init_json()
    db = await get_db()

    print("Starting migration from JSON to SQLite...")

    # Get data from JSON storage
    from api.database import _load_all

    try:
        # Migrate users
        print("Migrating users...")
        users = await _load_all("users")
        for user in users:
            await db._execute(
                """INSERT OR REPLACE INTO users 
                   (id, name, email, role, avatar_url, total_bounties, total_earnings, created_at, last_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user.get("id"),
                    user.get("name", ""),
                    user.get("email"),
                    user.get("role", "researcher"),
                    user.get("avatar_url"),
                    user.get("total_bounties", 0),
                    user.get("total_earnings", 0.0),
                    user.get("created_at", ""),
                    user.get("last_active", ""),
                ),
            )
        print(f"  Migrated {len(users)} users")

        # Migrate targets
        print("Migrating targets...")
        targets = await _load_all("targets")
        for target in targets:
            await db._execute(
                """INSERT OR REPLACE INTO targets 
                   (id, program_name, scope, link, platform, payout_tier, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    target.get("id"),
                    target.get("program_name", ""),
                    target.get("scope", ""),
                    target.get("link"),
                    target.get("platform"),
                    target.get("payout_tier", "MEDIUM"),
                    target.get("status", "ACTIVE"),
                    target.get("created_at", ""),
                ),
            )
        print(f"  Migrated {len(targets)} targets")

        # Migrate bounties
        print("Migrating bounties...")
        bounties = await _load_all("bounties")
        for bounty in bounties:
            await db._execute(
                """INSERT OR REPLACE INTO bounties 
                   (id, user_id, target_id, title, description, severity, status, reward, submitted_at, resolved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    bounty.get("id"),
                    bounty.get("user_id", ""),
                    bounty.get("target_id", ""),
                    bounty.get("title", ""),
                    bounty.get("description"),
                    bounty.get("severity", "MEDIUM"),
                    bounty.get("status", "PENDING"),
                    bounty.get("reward", 0.0),
                    bounty.get("submitted_at", ""),
                    bounty.get("resolved_at"),
                ),
            )
        print(f"  Migrated {len(bounties)} bounties")

        # Migrate sessions
        print("Migrating sessions...")
        sessions = await _load_all("sessions")
        for session in sessions:
            await db._execute(
                """INSERT OR REPLACE INTO sessions 
                   (id, user_id, mode, target_scope, progress, status, started_at, ended_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session.get("id"),
                    session.get("user_id", ""),
                    session.get("mode", ""),
                    session.get("target_scope"),
                    session.get("progress", 0),
                    session.get("status", "ACTIVE"),
                    session.get("started_at", ""),
                    session.get("ended_at"),
                ),
            )
        print(f"  Migrated {len(sessions)} sessions")

        # Migrate activity log
        print("Migrating activity log...")
        activities = await _load_all("activity_log")
        for activity in activities:
            metadata = activity.get("metadata")
            if metadata and not isinstance(metadata, str):
                metadata = json.dumps(metadata)

            await db._execute(
                """INSERT OR REPLACE INTO activity_log 
                   (id, user_id, action_type, description, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    activity.get("id"),
                    activity.get("user_id"),
                    activity.get("action_type", ""),
                    activity.get("description"),
                    metadata,
                    activity.get("created_at", ""),
                ),
            )
        print(f"  Migrated {len(activities)} activities")

        # Commit all changes
        await db._connection.commit()

        # Verify migration
        print("\nVerifying migration...")
        cursor = await db._execute("SELECT COUNT(*) as count FROM users")
        user_count = (await cursor.fetchone())["count"]
        cursor = await db._execute("SELECT COUNT(*) as count FROM targets")
        target_count = (await cursor.fetchone())["count"]
        cursor = await db._execute("SELECT COUNT(*) as count FROM bounties")
        bounty_count = (await cursor.fetchone())["count"]
        cursor = await db._execute("SELECT COUNT(*) as count FROM sessions")
        session_count = (await cursor.fetchone())["count"]
        cursor = await db._execute("SELECT COUNT(*) as count FROM activity_log")
        activity_count = (await cursor.fetchone())["count"]

        print(f"SQLite database summary:")
        print(f"  Users: {user_count}")
        print(f"  Targets: {target_count}")
        print(f"  Bounties: {bounty_count}")
        print(f"  Sessions: {session_count}")
        print(f"  Activities: {activity_count}")

        print("\n✅ Migration completed successfully!")
        print(f"SQLite database created at: {db.db_path}")

    finally:
        # Close connections
        await close_json()
        await db.disconnect()


async def backup_existing_database():
    """Create a backup of the existing JSON database."""
    import shutil
    from datetime import datetime

    db_dir = PROJECT_ROOT / "data" / "db"
    if db_dir.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = PROJECT_ROOT / "data" / f"db_backup_{timestamp}"

        print(f"Creating backup of existing JSON database...")
        shutil.copytree(db_dir, backup_dir)
        print(f"Backup created at: {backup_dir}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate JSON database to SQLite")
    parser.add_argument(
        "--backup", action="store_true", help="Create backup before migration"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force migration without confirmation"
    )

    args = parser.parse_args()

    # Confirm migration
    if not args.force:
        print("⚠️  WARNING: This will migrate data from JSON to SQLite database.")
        print(
            "   The JSON files will NOT be deleted, but SQLite will become the primary database."
        )
        response = input("Continue? (y/N): ")
        if response.lower() != "y":
            print("Migration cancelled.")
            sys.exit(0)

    # Create backup if requested
    if args.backup:
        asyncio.run(backup_existing_database())

    # Run migration
    asyncio.run(migrate_data())
