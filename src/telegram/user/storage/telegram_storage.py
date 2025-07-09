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

    def __init__(self, name: str, telegram_id: int, database_instance: Database):
        super().__init__(name)

        self.telegram_id: int = telegram_id
        self.database_instance: Database = database_instance

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
        raise NotImplementedError

    async def close(self) -> None:
        assert self.database_instance is not None, "Database instance is not set"
        await self.database_instance.close()

    async def delete(self) -> None:
        raise NotImplementedError

    async def create_session(
        self,
        dc_id: int,
        api_id: int,
        test_mode: bool,
        auth_key: bytes,
        user_id: int,
        is_bot: bool,
    ) -> None:
        assert self.database_instance is not None, "Database instance is not set"
        assert self.telegram_id is not None, "Telegram ID is not set"

    async def update_peers(
        self,
        peers: list[tuple[int, int, str, str]],
    ) -> None:
        assert self.database_instance is not None, "Database instance is not set"
        assert self.telegram_id is not None, "Telegram ID is not set"

        if len(peers) == 0:
            return

        peers_list = [
            TelegramPeers(
                owner_id=self.telegram_id,
                id=peer[0],
                access_hash=peer[1],
                type=peer[2],
                phone_number=peer[3],
            )
            for peer in peers
        ]

        async with self.database_instance.session() as session:
            await TelegramPeers.update_many(self.telegram_id, peers_list, session)

    async def update_usernames(self, usernames: list[tuple[int, list[str]]]) -> None:
        assert self.database_instance is not None, "Database instance is not set"
        assert self.telegram_id is not None, "Telegram ID is not set"

        if len(usernames) == 0:
            return

        usernames_to_add = [
            TelegramUsernames(owner_id=self.telegram_id, id=id, username=username)
            for id, usernames in usernames
            for username in usernames
        ]

        async with self.database_instance.session() as session:
            await TelegramUsernames.update_many(
                self.telegram_id, usernames_to_add, session
            )

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
        assert self.database_instance is not None, "Database instance is not set"
        assert self.telegram_id is not None, "Telegram ID is not set"

        async with self.database_instance.session() as session:
            peer = await TelegramPeers.get_by_id(self.telegram_id, peer_id, session)

            if peer is None:
                raise KeyError(f"ID not found: {peer_id}")

            return get_input_peer(peer.id, peer.access_hash, peer.type)

    async def get_peer_by_username(self, username: str):
        assert self.database_instance is not None, "Database instance is not set"
        assert self.telegram_id is not None, "Telegram ID is not set"

        async with self.database_instance.session() as session:
            peer = await TelegramPeers.get_by_username(
                self.telegram_id, username, session
            )

            if peer is None:
                raise KeyError(f"Username not found: {username}")

            if abs(time.time() - peer.last_update_on) > self.USERNAMES_TTL:
                raise KeyError(f"Username expired: {username}")

            return get_input_peer(peer.id, peer.access_hash, peer.type)

    async def get_peer_by_phone_number(self, phone_number: str):
        assert self.database_instance is not None, "Database instance is not set"
        assert self.telegram_id is not None, "Telegram ID is not set"

        async with self.database_instance.session() as session:
            peer = await TelegramPeers.get_by_phone_number(
                self.telegram_id, phone_number, session
            )

            if peer is None:
                raise KeyError(f"Phone number not found: {phone_number}")

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
