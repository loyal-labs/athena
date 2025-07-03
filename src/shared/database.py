import asyncio
import logging
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any

from sqlalchemy import URL, Result
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql import text
from sqlmodel import SQLModel

from src.shared.secrets import OnePasswordManager, SecretsFactory

logger = logging.getLogger("athena.database")


class DatabaseEnvFields(Enum):
    DATABASE = "database"
    USER = "username"
    PASSWORD = "password"


class Database:
    default_item_name = "ATHENA_POSTGRES"
    default_host = "localhost"
    default_port = 5432

    def __init__(self):
        # Constants
        self.host = self.default_host
        self.port = self.default_port

        # From 1Password
        self.user: str | None = None
        self.db_name: str | None = None
        self.password: str | None = None

        # Post init variables
        self.url: URL | None = None
        self.safe_url: URL | None = None

        self.engine: AsyncEngine | None = None
        self.async_session: async_sessionmaker[AsyncSession] | None = None

        logger.debug("Attempting to connect using effective URL: %s", self.safe_url)

    @classmethod
    async def create(cls):
        secrets_manager = await SecretsFactory.get_instance()
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

    async def __init_db(self, secrets_manager: OnePasswordManager):
        assert secrets_manager is not None, "Secrets manager is not set"
        assert isinstance(secrets_manager, OnePasswordManager), (
            "Secrets manager is not an instance of OnePasswordManager"
        )

        fetched_secrets = await secrets_manager.get_secret_item(self.default_item_name)
        self.user = fetched_secrets.get(DatabaseEnvFields.USER.value)
        self.db_name = fetched_secrets.get(DatabaseEnvFields.DATABASE.value)
        self.password = fetched_secrets.get(DatabaseEnvFields.PASSWORD.value)

        print(self.user, self.db_name, self.password)
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

    async def run_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]] | None:
        """
        Runs a query and returns the result.

        If the query is a SELECT, WITH, or RETURNING query,
        it returns a list of dictionaries.
        Otherwise, it returns None.
        """
        assert self.engine is not None, "Engine is not set"
        assert self.async_session is not None, "Async session is not set"

        # replace pycog sql params with sqlalchemy params
        query = re.sub(r"%\((\w+)\)s", r":\1", query)

        async with self.session() as session:
            query = query.strip()
            result = await session.execute(text(query), params)

            if query.startswith(("SELECT", "WITH", "RETURNING")):
                return [
                    dict(zip(result.keys(), row, strict=False))
                    for row in result.fetchall()
                ]
            else:
                # Returns None
                return []

    async def run_insert_query_with_id(
        self, query: str, params: dict[str, Any] | None = None
    ) -> int | None:
        """
        Runs an INSERT query and returns the last inserted row ID.
        """
        assert self.engine is not None, "Engine is not set"
        assert self.async_session is not None, "Async session is not set"

        # replace pycog sql params with sqlalchemy params
        query = re.sub(r"%\((\w+)\)s", r":\1", query)

        async with self.session() as session:
            await session.execute(text(query), params)

            result = await session.execute(text("SELECT LAST_INSERT_ID() as id"))
            row = result.first()

            await session.commit()
            return row.id if row else None

    async def execute_in_transaction(
        self, queries: list[str], params: dict[str, Any]
    ) -> bool:
        """Execute multiple queries in a single transaction"""
        async with self.session() as session:
            async with session.begin():
                try:
                    for query in queries:
                        converted_query = re.sub(r"%\((\w+)\)s", r":\1", query)
                        stmt = text(converted_query)
                        await session.execute(stmt, params)
                    return True
                except Exception as e:
                    await session.rollback()
                    raise e

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


class DatabaseFactory:
    """Global singleton factory for Database."""

    _instance: Database | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> Database:
        """Get or create singleton instance of Database."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    logger.info("Creating Database singleton")
                    cls._instance = await Database.create()
                    logger.info("Database singleton created")
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None
