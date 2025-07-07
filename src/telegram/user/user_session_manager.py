import asyncio
import base64
import logging
import struct
from collections import OrderedDict
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.telegram.user.login.login_schemas import LoginSession
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
                return self._sessions[owner_id]

            # Get session from database
            login_sessions = await LoginSession.get_by_owner(owner_id, db_session)
            if not login_sessions:
                raise ValueError(f"No session found for owner_id: {owner_id}")

            # Use the most recent session
            login_session = sorted(
                login_sessions, key=lambda x: x.updated_at, reverse=True
            )[0]

            # Evict old sessions if at capacity
            if len(self._sessions) >= self._max_sessions:
                await self._evict_lru_session()

            # Create new TelegramUser from session string
            user_session = await self._create_session_from_string(
                login_session.session_string
            )

            # Start the session
            await user_session.start()

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
        user_id: int,
        db_session: AsyncSession,
    ) -> TelegramUser:
        """
        Create a completely new session and save to database.

        Args:
            owner_id: The owner ID for the session
            dc_id: Telegram data center ID
            auth_key: Authentication key (256 bytes)
            user_id: Telegram user ID
            db_session: Database session

        Returns:
            TelegramUser instance
        """
        # Create TelegramUser instance
        user_session = await TelegramUser.create(dc_id, auth_key, user_id)

        # Save to database
        assert user_session.session_string is not None, "Session string is None"
        login_session, created = await LoginSession.get_or_create(
            owner_id=owner_id,
            session_string=user_session.session_string,
            session=db_session,
        )

        if not created:
            # Update the existing session
            login_session.updated_at = datetime.now()
            await db_session.commit()

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

    async def _create_session_from_string(self, session_string: str) -> TelegramUser:
        """Create a TelegramUser instance from a session string."""
        # Decode session string to get components
        dc_id, _, _, auth_key, user_id, _ = self._decode_session_string(session_string)

        # Create TelegramUser with decoded values
        return await TelegramUser.create(dc_id, auth_key, user_id)

    def _decode_session_string(self, session_string: str):
        """Decode a Pyrogram session string."""
        # Add padding if needed
        padding = 4 - len(session_string) % 4
        if padding != 4:
            session_string += "=" * padding

        # Decode from base64
        decoded = base64.urlsafe_b64decode(session_string)

        # Unpack the binary data
        dc_id, api_id, test_mode, auth_key, user_id, is_bot = struct.unpack(
            ">BI?256sQ?", decoded
        )

        return dc_id, api_id, test_mode, auth_key, user_id, is_bot

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
