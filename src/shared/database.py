import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, cast

from sqlalchemy import URL, Result
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql import text
from sqlmodel import SQLModel

from src.shared.secrets import OnePasswordManager

logger = logging.getLogger("athena.database")


class DatabaseEnvFields(Enum):
    DATABASE = "database"
    USER = "username"
    PASSWORD = "password"


class PostgreSQL:
    default_item_name = "ATHENA_POSTGRES"
    default_host = "localhost"
    default_port = 5432

    def __init__(self):
        # Constants
        self.host = self.default_host
        self.port = self.default_port

        # From 1Password
        self.user = None
        self.db_name = None
        self.password = None

        # Post init variables
        self.url = None
        self.safe_url = None

        self.engine = None
        self.async_session = None

        logger.debug("Attempting to connect using effective URL: %s", self.safe_url)

    @classmethod
    async def create(cls, secrets_manager: OnePasswordManager):
        assert secrets_manager is not None, "Secrets manager is not set"
        assert isinstance(secrets_manager, OnePasswordManager), (
            "Secrets manager is not an instance of OnePasswordManager"
        )
        self = cls()
        await self.__init_db(secrets_manager)

        try:
            self.engine = create_async_engine(
                self.url,  # type: ignore
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
            raise

        await self.__post_init_checks()

        return self

    # --- Private Methods ---
    async def __post_init_checks(self):
        assert self.user is not None, "User is not set"
        assert self.db_name is not None, "Database name is not set"
        assert self.password is not None, "Password is not set"
        assert self.url is not None, "URL is not set"
        assert self.safe_url is not None, "Safe URL is not set"
        assert self.engine is not None, "Engine is not set"
        assert self.async_session is not None, "Async session is not set"

        self.engine = cast(AsyncEngine, self.engine)
        self.async_session = cast(async_sessionmaker[AsyncSession], self.async_session)  # type: ignore

    async def __init_db(self, secrets_manager: OnePasswordManager):
        assert secrets_manager is not None, "Secrets manager is not set"
        assert isinstance(secrets_manager, OnePasswordManager), (
            "Secrets manager is not an instance of OnePasswordManager"
        )
        self.user = await secrets_manager.get_secret(
            secrets_manager.default_vault,
            self.default_item_name,
            DatabaseEnvFields.USER.value,
        )
        self.db_name = await secrets_manager.get_secret(
            secrets_manager.default_vault,
            self.default_item_name,
            DatabaseEnvFields.DATABASE.value,
        )
        self.password = await secrets_manager.get_secret(
            secrets_manager.default_vault,
            self.default_item_name,
            DatabaseEnvFields.PASSWORD.value,
        )
        self.url = self.__build_sqlalchemy_url(use_placeholder_password=False)
        self.safe_url = self.__build_sqlalchemy_url(use_placeholder_password=True)

    def __build_sqlalchemy_url(self, use_placeholder_password: bool = False) -> URL:
        """Internal helper to construct the SQLAlchemy URL object."""
        password_to_use = "XXXXXX" if use_placeholder_password else self.password

        sqlalchemy_url = URL.create(
            drivername="postgresql+asyncpg",
            username=self.user,
            password=password_to_use,  # Use determined password
            host=self.host,
            port=self.port,
            database=self.db_name,
        )
        return sqlalchemy_url

    async def create_all(self):
        """
        Initializes the database connection and optionally creates tables.
        """
        logger.debug("Initializing database connection to %s", self.safe_url)
        assert self.engine is not None, "Engine is not set"

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
        assert self.engine is not None, "Engine is not set"

        async with self.engine.begin() as conn:
            for table in reversed(SQLModel.metadata.sorted_tables):
                # Use dialect-specific quoting for table names
                quoted_name = self.engine.dialect.identifier_preparer.quote(table.name)
                # Execute raw SQL with CASCADE
                await conn.execute(text(f"DROP TABLE IF EXISTS {quoted_name} CASCADE"))
        logger.info("Finished dropping tables (using CASCADE).")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provides a transactional database session."""
        assert self.async_session is not None, "Async session is not set"
        assert isinstance(self.async_session, async_sessionmaker), (
            "Async session is not an instance of async_sessionmaker"
        )

        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                logger.error("Session rollback due to error: %s", e, exc_info=True)
                await session.rollback()
                raise

    async def results_to_dict(self, results: Result[Any]) -> list[dict[str, Any]]:
        """
        Converts a SQLAlchemy Result object to a list of dictionaries.
        """
        rows = [dict(row._mapping) for row in results]  # type: ignore
        return rows

    async def close(self):
        """Closes the database connection pool."""
        assert self.engine is not None, "Engine is not set"
        logger.info("Closing database connection pool for %s", self.safe_url)
        await self.engine.dispose()
