import asyncio
import logging
from collections import OrderedDict
from collections.abc import Coroutine
from datetime import datetime, timedelta
from typing import Any

from pyrogram.handlers.handler import Handler
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.database import Database
from src.telegram.user.inbox.inbox_handlers import TelegramInboxHandlers
from src.telegram.user.onboarding.onboarding_schemas import OnboardingSchema
from src.telegram.user.storage.storage_schema import TelegramSessions
from src.telegram.user.telegram_user_client import TelegramUser

logger = logging.getLogger("athena.telegram.user.session_manager")


class UserSessionManager:
    """
    Manages multiple Telegram user sessions with LRU eviction and database persistence.

    Features:
    - Caches active sessions in memory with configurable limit
    - Uses LRU (Least Recently Used) eviction when limit is reached
    - Persists session data in database
    - Thread-safe with per-user locks
    - Automatic session lifecycle management
    """

    def __init__(
        self,
        max_sessions: int = 100,
        session_ttl: timedelta = timedelta(hours=1),
        check_interval: timedelta = timedelta(minutes=15),
    ):
        """
        Initialize the UserSessionManager.

        Args:
            max_sessions: Maximum number of sessions to keep in memory
            session_ttl: Time-to-live for inactive sessions
            check_interval: Interval for cleaning up expired sessions
        """
        self._sessions: OrderedDict[int, TelegramUser] = OrderedDict()
        self._locks: dict[int, asyncio.Lock] = {}
        self._max_sessions = max_sessions
        self._session_ttl = session_ttl
        self._check_interval = check_interval
        self._last_access: dict[int, datetime] = {}
        self._cleanup_task: asyncio.Task[None] | None = None
        self._global_lock = asyncio.Lock()

        # Start periodic cleanup task
        self._start_cleanup_task()

    def _start_cleanup_task(self):
        """Start the periodic cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def _periodic_cleanup(self):
        """Periodically clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(self._check_interval.total_seconds())
                await self._cleanup_expired_sessions()
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")

    async def _cleanup_expired_sessions(self):
        """Remove sessions that have exceeded TTL."""
        now = datetime.now()
        expired_owners: list[int] = []

        async with self._global_lock:
            for owner_id, last_access in self._last_access.items():
                if now - last_access > self._session_ttl:
                    expired_owners.append(owner_id)

            for owner_id in expired_owners:
                logger.info(f"Cleaning up expired session for owner {owner_id}")
                await self._remove_session(owner_id)

    async def get_or_create_session(
        self, owner_id: int, db_session: AsyncSession
    ) -> TelegramUser:
        """
        Get an existing session or create a new one.

        Args:
            owner_id: The owner ID of the session
            db_session: Database session for persistence

        Returns:
            TelegramUser instance

        Raises:
            ValueError: If no session exists for the owner_id
        """
        # Use per-user lock to prevent race conditions
        if owner_id not in self._locks:
            self._locks[owner_id] = asyncio.Lock()

        async with self._locks[owner_id]:
            # Check if session exists in memory
            if owner_id in self._sessions:
                self._last_access[owner_id] = datetime.now()
                self._sessions.move_to_end(owner_id)  # LRU update
                logger.debug("Returning existing MTProto session for owner")
                return self._sessions[owner_id]

            user_session_db = await TelegramSessions.get(owner_id, db_session)
            assert user_session_db is not None, "No session found for owner"
            logger.debug(f"Session found for owner {owner_id}")

            user_session = await TelegramUser.create(
                user_session_db.dc_id,
                user_session_db.auth_key,
                owner_id,
            )

            logger.debug("Creating new MTProto session for owner")

            # Setup handlers
            inbox_handlers = TelegramInboxHandlers().inbox_filters

            handlers = [
                *inbox_handlers,
            ]

            # Start the session
            logger.debug("Starting MTProto user session")
            print("Starting MTProto user session")
            await user_session.start(handlers=handlers)

            # Cache the session
            self._sessions[owner_id] = user_session
            self._last_access[owner_id] = datetime.now()

            logger.info(f"Created new session for owner {owner_id}")
            return user_session

    async def create_new_session(
        self,
        owner_id: int,
        dc_id: int,
        auth_key: bytes,
        db_session: AsyncSession,
    ) -> TelegramUser:
        """
        Create a completely new session and save to database.

        Starts the session and caches it in memory.

        Args:
            owner_id: The Telegram ID for the user
            dc_id: Telegram data center ID
            auth_key: Authentication key (256 bytes)
            db_session: Database session

        Returns:
            TelegramUser instance
        """

        # Create new session
        user_session = await TelegramUser.create(dc_id, auth_key, owner_id)

        # Save onboarding status
        await OnboardingSchema.create(
            owner_id=owner_id,
            session=db_session,
        )

        # Use per-user lock
        if owner_id not in self._locks:
            self._locks[owner_id] = asyncio.Lock()

        async with self._locks[owner_id]:
            # Evict if at capacity
            if len(self._sessions) >= self._max_sessions:
                await self._evict_lru_session()

            # Start and cache the session
            await user_session.start()
            self._sessions[owner_id] = user_session
            self._last_access[owner_id] = datetime.now()

        logger.info(f"Created brand new session for owner {owner_id}")
        return user_session

    async def _evict_lru_session(self):
        """Remove the least recently used session."""
        owner_id, session = self._sessions.popitem(last=False)
        logger.info(f"Evicting LRU session for owner {owner_id}")

        try:
            await session.stop()
        except Exception as e:
            logger.error(f"Error stopping evicted session: {e}")

        del self._last_access[owner_id]

    async def _remove_session(self, owner_id: int):
        """Remove a specific session."""
        if owner_id in self._sessions:
            session = self._sessions.pop(owner_id)
            try:
                await session.stop()
            except Exception as e:
                logger.error(f"Error stopping session for owner {owner_id}: {e}")

        if owner_id in self._last_access:
            del self._last_access[owner_id]

    async def stop_session(self, owner_id: int):
        """
        Manually stop and remove a session.

        Args:
            owner_id: The owner ID of the session to stop
        """
        async with self._global_lock:
            await self._remove_session(owner_id)
            logger.info(f"Manually stopped session for owner {owner_id}")

    async def stop_all_sessions(self):
        """Stop all active sessions (useful for shutdown)."""
        logger.info("Stopping all active sessions...")

        # Cancel cleanup task
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

        # Stop all sessions
        for owner_id in list(self._sessions.keys()):
            await self._remove_session(owner_id)

        self._locks.clear()
        logger.info("All sessions stopped")

    def get_active_session_count(self) -> int:
        """Get the number of active sessions."""
        return len(self._sessions)

    def get_session_info(self) -> dict[int, datetime]:
        """Get information about active sessions."""
        return dict(self._last_access)

    def is_session_active(self, owner_id: int) -> bool:
        """Check if a session is currently active in memory."""
        return owner_id in self._sessions

    async def extend_session_ttl(self, owner_id: int) -> bool:
        """
        Extend the TTL for a specific session to keep it alive.

        This should be called when there's activity on the session to prevent
        it from being evicted due to TTL expiration.

        Args:
            owner_id: The owner ID of the session to extend

        Returns:
            True if session was found and extended, False otherwise
        """
        if owner_id not in self._sessions:
            return False

        # Update last access time to current time
        self._last_access[owner_id] = datetime.now()

        # Also update LRU order to mark as recently used
        self._sessions.move_to_end(owner_id)

        logger.debug(f"Extended TTL for session owner {owner_id}")
        return True

    async def extend_session_ttl_batch(self, owner_ids: list[int]) -> dict[int, bool]:
        """
        Extend TTL for multiple sessions at once.

        Args:
            owner_ids: List of owner IDs to extend

        Returns:
            Dictionary mapping owner_id to success status
        """
        results: dict[int, bool] = {}
        for owner_id in owner_ids:
            results[owner_id] = await self.extend_session_ttl(owner_id)
        return results

    async def load_all_sessions(self, db: Database, handlers: list[Handler]):
        """Load all sessions from the database."""
        async with db.session() as session:
            sessions = await TelegramSessions.get_all(session)

        logger.info(f"Loading {len(sessions)} sessions from the database")

        # Create all TelegramUser instances first
        telegram_users: list[tuple[int, TelegramUser]] = []
        for session in sessions:
            try:
                user = await TelegramUser.create(
                    session.dc_id,
                    session.auth_key,
                    session.owner_id,
                )
                telegram_users.append((session.owner_id, user))
            except Exception as e:
                logger.error(
                    f"Failed to create session for owner {session.owner_id}: {e}"
                )

        # Start all clients concurrently (inspired by compose)
        start_tasks: list[Coroutine[Any, Any, None]] = []

        for _, user in telegram_users:
            start_tasks.append(user.start(handlers=handlers))

        await asyncio.gather(*start_tasks, return_exceptions=True)

        # Cache all successfully started sessions
        for owner_id, user in telegram_users:
            self._sessions[owner_id] = user
            self._last_access[owner_id] = datetime.now()

        logger.info(f"Loaded {len(telegram_users)} sessions from the database")


class UserSessionFactory:
    """Factory for getting the UserSessionManager singleton instance."""

    _instance: UserSessionManager | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_instance(
        cls,
        max_sessions: int = 100,
        session_ttl: timedelta = timedelta(hours=1),
        check_interval: timedelta = timedelta(minutes=15),
    ) -> UserSessionManager:
        """Get or create the singleton UserSessionManager instance."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = UserSessionManager(
                        max_sessions=max_sessions,
                        session_ttl=session_ttl,
                        check_interval=check_interval,
                    )
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None
