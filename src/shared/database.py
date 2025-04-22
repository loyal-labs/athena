import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql import text
from sqlmodel import SQLModel

from src.shared.config import PostgresConfig

logger = logging.getLogger("athena.database")


class Database:
    def __init__(self, db_config: PostgresConfig):
        self.user = db_config.user
        self.host = db_config.host
        self.port = db_config.port
        self.db_name = db_config.db_name

        self.url = db_config.db_url
        self.safe_url = db_config.safe_db_url  # safe version for logging

        logger.debug("Attempting to connect using effective URL: %s", self.safe_url)

        try:
            self.engine = create_async_engine(
                self.url,
                echo=False,
                pool_pre_ping=True,
                pool_recycle=3600,
            )

            self.async_session = async_sessionmaker(
                bind=self.engine, class_=AsyncSession, expire_on_commit=False
            )
            logger.info("Async Database engine initialized for %s", self.safe_url)
        except Exception as e:
            logger.error(
                "Failed to initialize database engine for %s: %s",
                self.safe_url,
                e,
                exc_info=True,
            )
            # Consider raising the exception or handling it based on application needs
            raise

    async def create_all(self):
        """
        Initializes the database connection and optionally creates tables.
        """
        logger.debug("Initializing database connection to %s", self.safe_url)

        async with self.engine.begin() as conn:
            # TODO: Add Alembic migrations
            logger.warning(
                "Running SQLModel.metadata.create_all. Use Alembic for production."
            )
            await conn.run_sync(SQLModel.metadata.create_all)

        logger.debug("Database connection initialized, tables checked/created.")
        return self

    async def drop_all(self):
        """
        Drops all tables defined in SQLModel.metadata using CASCADE.
        WARNING: This is destructive and irreversible. Use with extreme caution.
        """
        logger.warning(
            "Dropping all tables in database %s defined in metadata (using CASCADE)!",
            self.safe_url,
        )
        async with self.engine.begin() as conn:
            for table in reversed(SQLModel.metadata.sorted_tables):
                # Use dialect-specific quoting for table names
                quoted_name = self.engine.dialect.identifier_preparer.quote(table.name)
                # Execute raw SQL with CASCADE
                await conn.execute(text(f"DROP TABLE IF EXISTS {quoted_name} CASCADE"))
        logger.info("Finished dropping tables (using CASCADE).")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        """Provides a transactional database session."""
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                logger.error("Session rollback due to error: %s", e, exc_info=True)
                await session.rollback()
                raise

    async def close(self):
        """Closes the database connection pool."""
        logger.info("Closing database connection pool for %s", self.safe_url)
        await self.engine.dispose()
