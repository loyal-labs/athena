#!/usr/bin/env python
"""Wait for database connection before running migrations."""

import asyncio
import logging
import os
import sys
from pathlib import Path

from sqlalchemy import text

project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from src.shared.database import DatabaseFactory  # noqa: E402

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


async def main():
    """Main function to wait for database connection."""
    logger.info("Waiting for database to be ready...")

    # Wait for database to be ready
    if not await wait_for_database():
        logger.error("Database is not available after maximum retries")
        sys.exit(1)

    logger.info("Database is ready! You can now run migrations.")


if __name__ == "__main__":
    asyncio.run(main())
