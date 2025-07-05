import time
from typing import Any, overload

from pyrogram import raw, utils
from pyrogram.client import Client
from pyrogram.storage.storage import Storage
from sqlalchemy import BigInteger, LargeBinary, event
from sqlalchemy.orm import aliased
from sqlmodel import Field, Relationship, SQLModel, col, delete, select

from src.shared.database import Database, DatabaseFactory


class SessionModel(SQLModel, table=True):
    __tablename__ = "sessions"  # type: ignore

    session_name: str = Field(primary_key=True)
    dc_id: int | None = Field(default=None)
    api_id: int | None = Field(default=None)
    test_mode: bool | None = Field(default=None)
    auth_key: bytes | None = Field(sa_type=LargeBinary, default=None)
    date: int = Field()
    user_id: int | None = Field(sa_type=BigInteger, default=None)
    is_bot: bool | None = Field(default=None)

    peers: list["PeerModel"] = Relationship(back_populates="session")


class PeerModel(SQLModel, table=True):
    __tablename__ = "peers"  # type: ignore

    session_name: str = Field(foreign_key="sessions.session_name", primary_key=True)
    id: int = Field(sa_type=BigInteger, primary_key=True)
    access_hash: int = Field(sa_type=BigInteger)
    type: str = Field()
    phone_number: str | None = Field(default=None)
    last_update_on: int | None = Field(sa_type=BigInteger, default=None)

    session: SessionModel | None = Relationship(back_populates="peers")


@event.listens_for(PeerModel, "before_update")
def update_last_update_on(mapper: Any, connection: Any, target: PeerModel) -> None:
    if not target.last_update_on:
        target.last_update_on = int(time.time())


class UsernameModel(SQLModel, table=True):
    __tablename__ = "usernames"  # type: ignore

    session_name: str = Field(foreign_key="peers.session_name", primary_key=True)
    id: int = Field(sa_type=BigInteger, foreign_key="peers.id", primary_key=True)
    username: str = Field(primary_key=True)


class UpdateStateModel(SQLModel, table=True):
    __tablename__ = "update_state"  # type: ignore

    id: int = Field(primary_key=True)
    session_name: str = Field(foreign_key="sessions.session_name")
    pts: int | None = Field(default=None)
    qts: int | None = Field(default=None)
    date: int | None = Field(default=None)
    seq: int | None = Field(default=None)


class VersionModel(SQLModel, table=True):
    __tablename__ = "version"  # type: ignore
    number: int = Field(primary_key=True)


def get_input_peer(peer_id: int, access_hash: int, peer_type: str):
    if peer_type in ["user", "bot"]:
        return raw.types.InputPeerUser(user_id=peer_id, access_hash=access_hash)  # type: ignore

    if peer_type == "group":
        return raw.types.InputPeerChat(chat_id=-peer_id)  # type: ignore

    if peer_type in ["channel", "supergroup"]:
        return raw.types.InputPeerChannel(  # type: ignore
            channel_id=utils.get_channel_id(peer_id), access_hash=access_hash
        )

    raise ValueError(f"Invalid peer type: {peer_type}")


class MultiPostgresStorage(Storage):
    VERSION = 1
    USERNAME_TTL = 8 * 60 * 60

    def __init__(self, client: Client, database: dict[str, str]):
        super().__init__(client.name)
        self.database = DatabaseFactory.get_instance()

    async def create(self):
        assert self.database is not None, "Database is not initialized"
        assert isinstance(self.database, Database), (
            "Database is not a Database instance"
        )

        async with self.database.session() as session:
            session_exists = await session.execute(
                select(SessionModel).where(SessionModel.session_name == self.name)
            )
            session_exists = session_exists.scalar()

            if not session_exists:
                new_session = SessionModel(
                    session_name=self.name,
                    dc_id=None,
                    api_id=None,
                    test_mode=None,
                    auth_key=None,
                    date=int(time.time()),
                    user_id=None,
                    is_bot=None,
                )
                session.add(new_session)
                await session.commit()

    async def open(self):
        assert self.database is not None, "Database is not initialized"
        assert isinstance(self.database, Database), (
            "Database is not a Database instance"
        )

        async with self.database.session() as session:
            session_exists = await session.execute(
                select(SessionModel).where(SessionModel.session_name == self.name)
            )
            session_exists = session_exists.scalar()
            if not session_exists:
                await self.create()

    async def save(self):
        assert self.database is not None, "Database is not initialized"
        assert isinstance(self.database, Database), (
            "Database is not a Database instance"
        )

        async with self.database.session() as session:
            await self.date(int(time.time()))
            await session.commit()

    async def close(self):
        assert self.database is not None, "Database is not initialized"
        assert isinstance(self.database, Database), (
            "Database is not a Database instance"
        )
        assert self.database.engine is not None, "Database engine is not initialized"

        async with self.database.session() as session:
            await session.close()
        await self.database.engine.dispose()

    async def delete(self):
        assert self.database is not None, "Database is not initialized"
        assert isinstance(self.database, Database), (
            "Database is not a Database instance"
        )

        async with self.database.session() as session:
            stmt = delete(UpdateStateModel).where(
                col(UpdateStateModel.session_name) == self.name
            )
            await session.execute(stmt)

            stmt = delete(UsernameModel).where(
                col(UsernameModel.session_name) == self.name
            )
            await session.execute(stmt)

            stmt = delete(PeerModel).where(col(PeerModel.session_name) == self.name)
            await session.execute(stmt)

            stmt = delete(SessionModel).where(
                col(SessionModel.session_name) == self.name
            )
            await session.execute(stmt)

            await session.commit()

    async def update_peers(self, peers: list[tuple[int, int, str, str]]):
        assert self.database is not None, "Database is not initialized"
        assert isinstance(self.database, Database), (
            "Database is not a Database instance"
        )

        async with self.database.session() as session:
            for peer in peers:
                stmt = select(PeerModel).where(
                    PeerModel.session_name == self.name, PeerModel.id == peer[0]
                )
                result = await session.execute(stmt)
                existing_peer = result.scalar_one_or_none()

                if existing_peer:
                    existing_peer.access_hash = peer[1]
                    existing_peer.type = peer[2]
                    existing_peer.phone_number = peer[3]
                else:
                    new_peer = PeerModel(
                        session_name=self.name,
                        id=peer[0],
                        access_hash=peer[1],
                        type=peer[2],
                        phone_number=peer[3],
                    )
                    session.add(new_peer)

            await session.commit()

    async def update_usernames(self, usernames: list[tuple[int, list[str]]]):
        assert self.database is not None, "Database is not initialized"
        assert isinstance(self.database, Database), (
            "Database is not a Database instance"
        )

        async with self.database.session() as session:
            for telegram_id, _ in usernames:
                stmt = delete(UsernameModel).where(
                    col(UsernameModel.session_name) == self.name,
                    col(UsernameModel.id) == telegram_id,
                )
                await session.execute(stmt)

            for telegram_id, user_list in usernames:
                for username in user_list:
                    new_username = UsernameModel(
                        session_name=self.name, id=telegram_id, username=username
                    )
                    session.add(new_username)

            await session.commit()

    async def get_peer_by_id(self, peer_id_or_username: int | str):
        assert self.database is not None, "Database is not initialized"
        assert isinstance(self.database, Database), (
            "Database is not a Database instance"
        )
        assert isinstance(peer_id_or_username, int | str), (
            "peer_id_or_username must be an integer (ID) or string (Username)."
        )

        async with self.database.session() as session:
            if isinstance(peer_id_or_username, int):
                peer = await session.execute(
                    select(PeerModel).where(
                        PeerModel.session_name == self.name,
                        PeerModel.id == peer_id_or_username,
                    )
                )
                peer = peer.scalar_one_or_none()
                assert peer is not None, f"ID not found: {peer_id_or_username}"
                return get_input_peer(peer.id, peer.access_hash, peer.type)  # type: ignore

            else:
                r = await session.execute(
                    select(
                        PeerModel.id,
                        PeerModel.access_hash,
                        PeerModel.type,
                        PeerModel.last_update_on,
                    )
                    .join(UsernameModel, col(UsernameModel.id) == col(PeerModel.id))
                    .where(
                        col(UsernameModel.username) == peer_id_or_username,
                        col(UsernameModel.session_name) == self.name,
                        col(PeerModel.session_name) == self.name,
                    )
                    .order_by(PeerModel.last_update_on.desc())
                )
                r = r.fetchone()
                if r is None:
                    raise KeyError(f"Username not found: {peer_id_or_username}")
                if len(r) == 4:
                    peer_id, access_hash, peer_type, last_update_on = r
                else:
                    raise ValueError(
                        f"The result does not contain the expected tuple of values. Received: {r}"
                    )
                if last_update_on:
                    if abs(time.time() - last_update_on) > self.USERNAME_TTL:
                        raise KeyError(f"Username expired: {peer_id_or_username}")
                return get_input_peer(peer_id, access_hash, peer_type)

    async def get_peer_by_username(self, username: str):
        assert self.database is not None, "Database is not initialized"
        assert isinstance(self.database, Database), (
            "Database is not a Database instance"
        )

        async with self.database.session() as session:
            peer_alias = aliased(PeerModel)
            username_alias = aliased(UsernameModel)
            r = await session.execute(
                select(
                    peer_alias.id,
                    peer_alias.access_hash,
                    peer_alias.type,
                    peer_alias.last_update_on,
                )
                .join(username_alias, col(username_alias.id) == col(peer_alias.id))
                .where(
                    col(username_alias.username) == username,
                    col(username_alias.session_name) == self.name,
                )
                .order_by(peer_alias.last_update_on.desc())
            )
            r = r.fetchone()
            if r is None:
                raise KeyError(f"Username not found: {username}")

            peer_id, access_hash, peer_type, _ = r
            return get_input_peer(peer_id, access_hash, peer_type)

    async def update_state(
        self, value: tuple[int, int, int, int, int] | int | type[object] = object
    ):
        assert self.database is not None, "Database is not initialized"
        assert isinstance(self.database, Database), (
            "Database is not a Database instance"
        )

        async with self.database.session() as session:
            if isinstance(value, type(object)):
                result = await session.execute(
                    select(UpdateStateModel).where(
                        UpdateStateModel.session_name == self.name
                    )
                )
                return result.scalars().all()
            else:
                if isinstance(value, int):
                    stmt = delete(UpdateStateModel).where(
                        col(UpdateStateModel.session_name) == self.name,
                        col(UpdateStateModel.id) == value,
                    )
                    await session.execute(stmt)
                else:
                    stmt = select(UpdateStateModel).where(
                        UpdateStateModel.session_name == self.name,
                        UpdateStateModel.id == value[0],
                    )
                    state = await session.execute(stmt)
                    state_instance = state.scalar_one_or_none()

                    if state_instance:
                        state_instance.pts = value[1]
                        state_instance.qts = value[2]
                        state_instance.date = value[3]
                        state_instance.seq = value[4]
                    else:
                        state_instance = UpdateStateModel(
                            id=value[0],
                            session_name=self.name,
                            pts=value[1],
                            qts=value[2],
                            date=value[3],
                            seq=value[4],
                        )
                        session.add(state_instance)

                await session.commit()

    async def get_peer_by_phone_number(self, phone_number: str):
        assert self.database is not None, "Database is not initialized"
        assert isinstance(self.database, Database), (
            "Database is not a Database instance"
        )

        async with self.database.session() as session:
            r = await session.execute(
                select(PeerModel.id, PeerModel.access_hash, PeerModel.type).where(
                    PeerModel.session_name == self.name,
                    PeerModel.phone_number == phone_number,
                )
            )
            r = r.scalar_one_or_none()

            if r is None:
                raise KeyError(f"Phone number not found: {phone_number}")

            return get_input_peer(r.id, r.access_hash, r.type)

    async def _get(self, attr: str):
        assert self.database is not None, "Database is not initialized"
        assert isinstance(self.database, Database), (
            "Database is not a Database instance"
        )

        async with self.database.session() as session:
            result = await session.execute(
                select(getattr(SessionModel, attr)).where(
                    SessionModel.session_name == self.name
                )
            )
            return result.scalar_one_or_none()

    async def _set(self, attr: str, value: Any):
        assert self.database is not None, "Database is not initialized"
        assert isinstance(self.database, Database), (
            "Database is not a Database instance"
        )

        async with self.database.session() as session:
            session_instance = await session.execute(
                select(SessionModel).where(SessionModel.session_name == self.name)
            )
            session_instance = session_instance.scalar_one_or_none()

            if session_instance:
                setattr(session_instance, attr, value)
                await session.commit()
            else:
                raise ValueError(f"Session with name {self.name} not found.")

    async def _accessor(self, attr: str, value: Any = object):
        if isinstance(value, type(object)):
            return await self._get(attr)
        else:
            await self._set(attr, value)

    async def dc_id(self, value: int | type[object] = object):
        return await self._accessor("dc_id", value)

    async def api_id(self, value: int | type[object] = object):
        return await self._accessor("api_id", value)

    async def test_mode(self, value: bool | type[object] = object):
        return await self._accessor("test_mode", value)

    async def auth_key(self, value: bytes | type[object] = object):
        return await self._accessor("auth_key", value)

    async def date(self, value: int | type[object] = object):
        return await self._accessor("date", value)

    async def user_id(self, value: int | type[object] = object):
        return await self._accessor("user_id", value)

    async def is_bot(self, value: bool | type[object] = object):
        return await self._accessor("is_bot", value)

    async def version(self, value: int | type[object] = object):
        assert self.database is not None, "Database is not initialized"
        assert isinstance(self.database, Database), (
            "Database is not a Database instance"
        )

        async with self.database.session() as session:
            if isinstance(value, type(object)):
                result = await session.execute(select(VersionModel.number))
                return result.scalar_one_or_none()
            else:
                version_instance = await session.execute(select(VersionModel))
                version_instance = version_instance.scalar_one_or_none()

                if version_instance:
                    version_instance.number = value
                    await session.commit()
