#!/usr/bin/env python
"""Run Alembic migrations before starting the application."""

import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import text

from alembic import command
from alembic.config import Config
from src.shared.database import DatabaseFactory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_database_connection():
    """Check if database is reachable."""
    try:
        db = await DatabaseFactory.get_instance()
        async with db.session() as session:
            result = await session.execute(text("SELECT 1"))
            result.scalar()
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


async def wait_for_database(max_retries: int = 30, retry_delay: int = 2):
    """Wait for database to be ready."""
    for attempt in range(max_retries):
        if await check_database_connection():
            return True
        logger.info(f"Waiting for database... (attempt {attempt + 1}/{max_retries})")
        await asyncio.sleep(retry_delay)
    return False


def run_migrations():
    """Run Alembic migrations."""
    try:
        # Get the alembic.ini path
        alembic_ini_path = Path(__file__).parent.parent / "alembic.ini"

        if not alembic_ini_path.exists():
            logger.error(f"alembic.ini not found at {alembic_ini_path}")
            return False

        # Create Alembic configuration
        alembic_cfg = Config(str(alembic_ini_path))

        # Run migrations
        logger.info("Running database migrations...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Migrations completed successfully")
        return True
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


async def main():
    """Main function to coordinate database setup."""
    logger.info("Starting database migration process...")

    # Wait for database to be ready
    if not await wait_for_database():
        logger.error("Database is not available after maximum retries")
        sys.exit(1)

    # Run migrations
    if not run_migrations():
        logger.error("Failed to run migrations")
        sys.exit(1)

    logger.info("Database setup completed successfully")


if __name__ == "__main__":
    asyncio.run(main())
