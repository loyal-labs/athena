import asyncio
import time
from typing import Any

from pyrogram.raw.types.input_peer_channel import InputPeerChannel
from pyrogram.raw.types.input_peer_chat import InputPeerChat
from pyrogram.raw.types.input_peer_user import InputPeerUser
from pyrogram.storage.storage import Storage
from pyrogram.utils import get_channel_id

from src.shared.database import Database, DatabaseFactory
from src.telegram.user.storage.storage_schema import (
    TelegramPeers,
    TelegramSessions,
    TelegramUpdateState,
    TelegramUsernames,
    TelegramVersion,
)

SUPPORTED_PEER_TYPES = ["user", "bot", "group", "channel", "supergroup"]


def get_input_peer(
    peer_id: int, access_hash: int, peer_type: str
) -> InputPeerUser | InputPeerChat | InputPeerChannel:
    if peer_type in ["user", "bot"]:
        return InputPeerUser(user_id=peer_id, access_hash=access_hash)

    if peer_type == "group":
        return InputPeerChat(chat_id=-peer_id)

    if peer_type in ["channel", "supergroup"]:
        return InputPeerChannel(
            channel_id=get_channel_id(peer_id), access_hash=access_hash
        )

    raise ValueError(f"Invalid peer type: {peer_type}")


class PostgresStorage(Storage):
    VERSION = 1
    USERNAMES_TTL = 8 * 60 * 60

    # Batching settings
    BATCH_TIME = 5.0
    BATCH_SIZE = 50
    PEERS_THRESHOLD = 25

    def __init__(self, name: str, telegram_id: int, database_instance: Database):
        super().__init__(name)

        self.telegram_id: int = telegram_id
        self.database_instance: Database = database_instance

        # In-memory cache for immediate access
        self._peer_cache: dict[int, TelegramPeers] = {}  # peer_id -> TelegramPeers
        self._username_cache: dict[str, int] = {}  # username -> peer_id
        self._phone_cache: dict[str, int] = {}  # phone -> peer_id

        # Pending writes (still batch to database)
        self._pending_peers: dict[int, TelegramPeers] = {}  # peer_id -> TelegramPeers
        self._pending_usernames: dict[int, set[str]] = {}  # peer_id -> set of usernames
        self._last_flush_time = time.time()
        self._batch_lock = asyncio.Lock()
        self._operation_count = 0

    async def _should_flush(self) -> bool:
        """More aggressive flushing since we have cache."""
        current_time = time.time()
        return (
            self._operation_count >= self.BATCH_SIZE
            or len(self._pending_peers) >= self.PEERS_THRESHOLD
            or (current_time - self._last_flush_time) >= self.BATCH_TIME
        )

    async def _flush_batch(self, force: bool = False):
        """Flush to database while keeping cache intact."""
        async with self._batch_lock:
            if not force and not await self._should_flush():
                return

            if not self._pending_peers and not self._pending_usernames:
                return

            # Flush peers to database
            if self._pending_peers:
                peers_list = list(self._pending_peers.values())

                async with self.database_instance.no_auto_commit_session() as session:
                    await TelegramPeers.update_many(peers_list, session)
                    await session.commit()

                self._pending_peers.clear()

            # Flush usernames to database
            if self._pending_usernames:
                usernames_list = [
                    TelegramUsernames(
                        owner_id=self.telegram_id, id=peer_id, username=username
                    )
                    for peer_id, usernames in self._pending_usernames.items()
                    for username in usernames
                ]

                async with self.database_instance.no_auto_commit_session() as session:
                    await TelegramUsernames.update_many(usernames_list, session)
                    await session.commit()

                self._pending_usernames.clear()

            # Reset counters
            self._operation_count = 0
            self._last_flush_time = time.time()

    @classmethod
    async def create(
        cls,
        dc_id: int,
        api_id: int,
        auth_key: bytes,
        user_id: int,
        test_mode: bool = False,
        is_bot: bool = False,
    ) -> "PostgresStorage":
        database_instance = await DatabaseFactory.get_instance()

        assert database_instance is not None, "Database instance is not initialized"
        assert user_id is not None, "Telegram ID is not provided"
        assert isinstance(user_id, int), "Telegram ID must be an integer"
        assert dc_id > 0 and dc_id < 10, "DC ID must be between 1 and 10"

        self = cls(
            name=f"telegram_session_{user_id}",
            telegram_id=user_id,
            database_instance=database_instance,
        )

        async with database_instance.session() as session:
            await TelegramSessions.get_or_create(
                owner_id=user_id,
                dc_id=dc_id,
                api_id=api_id,
                test_mode=test_mode,
                auth_key=auth_key,
                user_id=user_id,
                is_bot=is_bot,
                session=session,
            )

        return self

    async def open(self) -> None:
        assert self.database_instance is not None, "Database instance is not set"
        assert self.telegram_id is not None, "Telegram ID is not set"

        async with self.database_instance.session() as session:
            result = await TelegramSessions.is_present(self.telegram_id, session)

            assert result is not None, "Session not found"
            assert result is True, "Session not found"

    async def save(self) -> None:
        """Force flush all pending operations."""
        await self._flush_batch(force=True)

    async def close(self) -> None:
        """Save and close."""
        await self.save()
        assert self.database_instance is not None, "Database instance is not set"
        await self.database_instance.close()

    async def delete(self) -> None:
        raise NotImplementedError

    async def update_peers(self, peers: list[tuple[int, int, str, str]]) -> None:
        """Update both cache and pending writes."""
        assert self.database_instance is not None, "Database instance is not set"
        assert self.telegram_id is not None, "Telegram ID is not set"

        if len(peers) == 0:
            return

        async with self._batch_lock:
            for peer in peers:
                peer_id, access_hash, peer_type, phone_number = peer

                # Create TelegramPeers object
                peer_obj = TelegramPeers(
                    owner_id=self.telegram_id,
                    id=peer_id,
                    access_hash=access_hash,
                    type=peer_type,
                    phone_number=phone_number,
                )

                # Update cache immediately (for instant access)
                self._peer_cache[peer_id] = peer_obj
                if phone_number:
                    self._phone_cache[phone_number] = peer_id

                # Queue for database write
                self._pending_peers[peer_id] = peer_obj

            self._operation_count += 1

        # Non-blocking flush check
        await self._flush_batch()

    async def update_usernames(self, usernames: list[tuple[int, list[str]]]) -> None:
        """Update both cache and pending writes."""
        assert self.database_instance is not None, "Database instance is not set"
        assert self.telegram_id is not None, "Telegram ID is not set"

        if len(usernames) == 0:
            return

        async with self._batch_lock:
            for peer_id, username_list in usernames:
                # Update cache immediately
                for username in username_list:
                    self._username_cache[username.lower()] = peer_id

                # Queue for database write
                if peer_id not in self._pending_usernames:
                    self._pending_usernames[peer_id] = set()
                self._pending_usernames[peer_id].update(username_list)

            self._operation_count += 1

        # Non-blocking flush check
        await self._flush_batch()

    async def update_state(  # type: ignore
        self, value: object | int | TelegramUpdateState = object
    ) -> list[TelegramUpdateState] | None:
        assert self.database_instance is not None, "Database instance is not set"
        assert self.telegram_id is not None, "Telegram ID is not set"

        async with self.database_instance.session() as session:
            if value is object:
                return await TelegramUpdateState.fetch_all(self.telegram_id, session)
            else:
                if isinstance(value, int):
                    await TelegramUpdateState.delete(self.telegram_id, value, session)
                elif isinstance(value, TelegramUpdateState):
                    await TelegramUpdateState.replace(self.telegram_id, value, session)

    async def get_peer_by_id(self, peer_id: int):
        """Check cache first, then database."""
        assert self.database_instance is not None, "Database instance is not set"
        assert self.telegram_id is not None, "Telegram ID is not set"

        # Check cache first (immediate access)
        if peer_id in self._peer_cache:
            peer = self._peer_cache[peer_id]
            return get_input_peer(peer.id, peer.access_hash, peer.type)

        # Fall back to database
        async with self.database_instance.session() as session:
            peer = await TelegramPeers.get_by_id(self.telegram_id, peer_id, session)

            if peer is None:
                raise KeyError(f"ID not found: {peer_id}")

            # Cache the result for future access
            async with self._batch_lock:
                self._peer_cache[peer_id] = peer

            return get_input_peer(peer.id, peer.access_hash, peer.type)

    async def get_peer_by_username(self, username: str):
        """Check cache first, then database."""
        assert self.database_instance is not None, "Database instance is not set"
        assert self.telegram_id is not None, "Telegram ID is not set"

        username_lower = username.lower()

        # Check cache first
        if username_lower in self._username_cache:
            peer_id = self._username_cache[username_lower]
            if peer_id in self._peer_cache:
                peer = self._peer_cache[peer_id]
                # Check TTL
                if abs(time.time() - peer.last_update_on) <= self.USERNAMES_TTL:
                    return get_input_peer(peer.id, peer.access_hash, peer.type)

        # Fall back to database
        async with self.database_instance.session() as session:
            peer = await TelegramPeers.get_by_username(
                self.telegram_id, username, session
            )

            if peer is None:
                raise KeyError(f"Username not found: {username}")

            if abs(time.time() - peer.last_update_on) > self.USERNAMES_TTL:
                raise KeyError(f"Username expired: {username}")

            # Cache the result
            async with self._batch_lock:
                self._peer_cache[peer.id] = peer
                self._username_cache[username_lower] = peer.id

            return get_input_peer(peer.id, peer.access_hash, peer.type)

    async def get_peer_by_phone_number(self, phone_number: str):
        """Check cache first, then database."""
        assert self.database_instance is not None, "Database instance is not set"
        assert self.telegram_id is not None, "Telegram ID is not set"

        # Check cache first
        if phone_number in self._phone_cache:
            peer_id = self._phone_cache[phone_number]
            if peer_id in self._peer_cache:
                peer = self._peer_cache[peer_id]
                return get_input_peer(peer.id, peer.access_hash, peer.type)

        # Fall back to database
        async with self.database_instance.session() as session:
            peer = await TelegramPeers.get_by_phone_number(
                self.telegram_id, phone_number, session
            )

            if peer is None:
                raise KeyError(f"Phone number not found: {phone_number}")

            # Cache the result
            async with self._batch_lock:
                self._peer_cache[peer.id] = peer
                self._phone_cache[phone_number] = peer.id

            return get_input_peer(peer.id, peer.access_hash, peer.type)

    async def _get_attribute(self, attr: str):
        assert self.database_instance is not None, "Database instance is not set"
        assert self.telegram_id is not None, "Telegram ID is not set"

        async with self.database_instance.session() as session:
            return await TelegramSessions.get_attribute(self.telegram_id, attr, session)

    async def _set_attribute(self, attr: str, value: Any):
        assert self.database_instance is not None, "Database instance is not set"
        assert self.telegram_id is not None, "Telegram ID is not set"

        async with self.database_instance.session() as session:
            await TelegramSessions.set_attribute(self.telegram_id, attr, value, session)

    async def dc_id(self, value: int | object = object):
        if value is object:
            return await self._get_attribute("dc_id")
        elif isinstance(value, int):
            await self._set_attribute("dc_id", value)
        else:
            raise ValueError("Invalid value type")

    async def api_id(self, value: int | object = object):
        if value is object:
            return await self._get_attribute("api_id")
        elif isinstance(value, int):
            await self._set_attribute("api_id", value)
        else:
            raise ValueError("Invalid value type")

    async def test_mode(self, value: bool | object = object):
        if value is object:
            return await self._get_attribute("test_mode")
        elif isinstance(value, bool):
            await self._set_attribute("test_mode", value)
        else:
            raise ValueError("Invalid value type")

    async def auth_key(self, value: bytes | object = object):
        if value is object:
            return await self._get_attribute("auth_key")
        elif isinstance(value, bytes):
            await self._set_attribute("auth_key", value)
        else:
            raise ValueError("Invalid value type")

    async def date(self, value: int | object = object):
        if value is object:
            return await self._get_attribute("date")
        elif isinstance(value, int):
            await self._set_attribute("date", value)
        else:
            raise ValueError("Invalid value type")

    async def user_id(self, value: int | object = object):
        if value is object:
            return await self._get_attribute("user_id")
        elif isinstance(value, int):
            await self._set_attribute("user_id", value)
        else:
            raise ValueError("Invalid value type")

    async def is_bot(self, value: bool | object = object):
        if value is object:
            return await self._get_attribute("is_bot")
        elif isinstance(value, bool):
            await self._set_attribute("is_bot", value)
        else:
            raise ValueError("Invalid value type")

    async def version(self, value: int | object = object):
        database_instance = await DatabaseFactory.get_instance()

        async with database_instance.session() as session:
            if value is object:
                return await TelegramVersion.get_number(session)
            elif isinstance(value, int):
                await TelegramVersion.set_number(value, session)
            else:
                raise ValueError("Invalid value type")
