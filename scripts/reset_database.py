#!/usr/bin/env python
"""Database management utilities for Alembic and testing."""

import argparse
import asyncio
import logging
from pathlib import Path

from sqlalchemy import text

from alembic import command
from alembic.config import Config
from src.shared.database import DatabaseFactory

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def truncate_all_tables():
    """Truncate all tables (remove data but keep structure)."""
    db = await DatabaseFactory.get_instance()

    async with db.session() as session:
        # Get all table names
        result = await session.execute(
            text("""
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = 'public' 
                AND tablename NOT IN ('alembic_version')
            """)
        )
        tables = [row[0] for row in result]

        if not tables:
            logger.info("No tables to truncate")
            return

        # Truncate all tables with CASCADE to handle foreign keys
        for table in tables:
            logger.info(f"Truncating table: {table}")
            await session.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))

        await session.commit()
        logger.info(f"Truncated {len(tables)} tables")


async def drop_all_tables():
    """Drop all tables including alembic version."""
    db = await DatabaseFactory.get_instance()

    # Use the existing drop_all method
    await db.drop_all()

    # Also drop alembic_version table
    async with db.session() as session:
        await session.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))
        await session.commit()

    logger.info("All tables dropped")


def downgrade_to_base():
    """Downgrade all migrations (removes all tables via migrations)."""
    alembic_ini_path = Path(__file__).parent.parent / "alembic.ini"

    if not alembic_ini_path.exists():
        logger.error(f"alembic.ini not found at {alembic_ini_path}")
        return False

    alembic_cfg = Config(str(alembic_ini_path))

    logger.info("Downgrading to base (removing all tables)...")
    command.downgrade(alembic_cfg, "base")
    logger.info("Downgrade completed")
    return True


def upgrade_to_head():
    """Re-run all migrations to recreate tables."""
    alembic_ini_path = Path(__file__).parent.parent / "alembic.ini"

    if not alembic_ini_path.exists():
        logger.error(f"alembic.ini not found at {alembic_ini_path}")
        return False

    alembic_cfg = Config(str(alembic_ini_path))

    logger.info("Running migrations to recreate schema...")
    command.upgrade(alembic_cfg, "head")
    logger.info("Schema recreated")
    return True


async def reset_specific_tables(table_names: list[str]):
    """Reset specific tables only."""
    db = await DatabaseFactory.get_instance()

    async with db.session() as session:
        for table in table_names:
            logger.info(f"Truncating table: {table}")
            try:
                await session.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
            except Exception as e:
                logger.error(f"Failed to truncate {table}: {e}")

        await session.commit()


async def main():
    parser = argparse.ArgumentParser(description="Reset database for testing")
    parser.add_argument(
        "--mode",
        choices=["truncate", "drop", "migrate-reset", "tables"],
        default="truncate",
        help="Reset mode: truncate (keep schema), drop (remove everything), migrate-reset (via alembic), tables (specific tables)",
    )
    parser.add_argument(
        "--tables", nargs="+", help="Specific tables to reset (only with --mode tables)"
    )
    parser.add_argument(
        "--confirm", action="store_true", help="Skip confirmation prompt"
    )

    args = parser.parse_args()

    # Confirmation prompt
    if not args.confirm:
        print(f"\n⚠️  WARNING: This will DELETE DATA using mode: {args.mode}")
        if args.mode == "tables" and args.tables:
            print(f"   Tables: {', '.join(args.tables)}")
        response = input("\nAre you sure? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted")
            return

    try:
        if args.mode == "truncate":
            # Just remove data, keep tables
            await truncate_all_tables()

        elif args.mode == "drop":
            # Drop everything and recreate
            await drop_all_tables()
            upgrade_to_head()

        elif args.mode == "migrate-reset":
            # Use alembic to downgrade then upgrade
            downgrade_to_base()
            upgrade_to_head()

        elif args.mode == "tables":
            # Reset specific tables
            if not args.tables:
                logger.error("No tables specified for reset")
                return
            await reset_specific_tables(args.tables)

        logger.info("✅ Database reset completed successfully")

    except Exception as e:
        logger.error(f"❌ Reset failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
