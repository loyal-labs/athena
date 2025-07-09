import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKeyConstraint,
    LargeBinary,
    PrimaryKeyConstraint,
    String,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel, col, delete, insert, select, update

logger = logging.getLogger("athena.telegram.user.storage.storage_schema")


class TelegramSessions(SQLModel, table=True):
    __tablename__ = "telegram_sessions"  # type: ignore

    owner_id: int = Field(sa_type=BigInteger, primary_key=True, unique=True)
    dc_id: int = Field(sa_type=BigInteger, primary_key=True)
    api_id: int = Field(sa_type=BigInteger)
    test_mode: bool = Field(sa_type=Boolean)
    auth_key: bytes = Field(sa_type=LargeBinary)
    date: int = Field(
        sa_type=BigInteger,
        nullable=False,
        default_factory=lambda: int(datetime.now().timestamp()),
    )
    user_id: int = Field(sa_type=BigInteger)
    is_bot: bool = Field(sa_type=Boolean)

    @classmethod
    async def get_or_create(
        cls,
        owner_id: int,
        dc_id: int,
        api_id: int,
        test_mode: bool,
        auth_key: bytes,
        user_id: int,
        is_bot: bool,
        session: AsyncSession,
    ) -> None:
        result = await session.execute(select(cls).where(col(cls.owner_id) == owner_id))
        if result.scalar_one_or_none() is not None:
            logger.debug(f"Session already exists for owner_id: {owner_id}")
            return

        logger.debug(f"Creating session for owner_id: {owner_id}")
        statement = insert(cls).values(
            owner_id=owner_id,
            dc_id=dc_id,
            api_id=api_id,
            test_mode=test_mode,
            auth_key=auth_key,
            date=int(datetime.now().timestamp()),
            user_id=user_id,
            is_bot=is_bot,
        )
        await session.execute(statement)
        await session.commit()

    @classmethod
    async def is_present(cls, owner_id: int, session: AsyncSession) -> bool:
        result = await session.execute(select(cls).where(col(cls.owner_id) == owner_id))
        return result.scalar_one_or_none() is not None

    @classmethod
    async def get(cls, owner_id: int, session: AsyncSession) -> "TelegramSessions":
        result = await session.execute(select(cls).where(col(cls.owner_id) == owner_id))
        fetched_result = result.scalar_one_or_none()
        assert fetched_result is not None, "Session not found"
        return fetched_result

    @classmethod
    async def get_attribute(
        cls, owner_id: int, attr: str, session: AsyncSession
    ) -> Any:
        stmt = select(cls).where(col(cls.owner_id) == owner_id)
        request = await session.execute(stmt)

        return getattr(request.scalar_one_or_none(), attr)  # type: ignore

    @classmethod
    async def set_attribute(
        cls, owner_id: int, attr: str, value: Any, session: AsyncSession
    ) -> None:
        stmt = update(cls).where(col(cls.owner_id) == owner_id).values({attr: value})
        await session.execute(stmt)


class TelegramPeers(SQLModel, table=True):
    __tablename__ = "telegram_peers"  # type: ignore
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id"],
            ["telegram_sessions.owner_id"],
            ondelete="CASCADE",
        ),
        PrimaryKeyConstraint("owner_id", "id", name="telegram_peers_pkey"),
    )

    owner_id: int = Field(sa_type=BigInteger)
    id: int = Field(sa_type=BigInteger, index=True)
    access_hash: int = Field(sa_type=BigInteger)
    type: str = Field(sa_type=String, nullable=False)
    phone_number: str = Field(sa_type=String, index=True, nullable=True)
    last_update_on: int = Field(
        sa_type=BigInteger,
        nullable=False,
        default_factory=lambda: int(datetime.now().timestamp()),
    )

    @classmethod
    async def get_by_id(
        cls, owner_id: int, id: int, session: AsyncSession
    ) -> Optional["TelegramPeers"]:
        statement = select(cls).where(col(cls.owner_id) == owner_id, col(cls.id) == id)
        result = await session.execute(statement)
        return result.scalar_one_or_none()  # type: ignore

    @classmethod
    async def get_by_username(
        cls, owner_id: int, username: str, session: AsyncSession
    ) -> Optional["TelegramPeers"]:
        statement = (
            select(cls)
            .join(
                TelegramUsernames,
                col(cls.id) == col(TelegramUsernames.id),
            )
            .where(
                TelegramUsernames.username == username,
                col(cls.owner_id) == owner_id,
            )
            .order_by(col(cls.last_update_on).desc())
            .limit(1)
        )
        result = await session.execute(statement)
        return result.scalar_one_or_none()  # type: ignore

    @classmethod
    async def get_by_phone_number(
        cls, owner_id: int, phone_number: str, session: AsyncSession
    ) -> Optional["TelegramPeers"]:
        statement = select(cls).where(
            col(cls.owner_id) == owner_id, col(cls.phone_number) == phone_number
        )
        result = await session.execute(statement)
        return result.scalar_one_or_none()  # type: ignore

    @classmethod
    async def update_many(
        cls, values: list["TelegramPeers"], session: AsyncSession
    ) -> None:
        assert values is not None, "Values is None"

        if len(values) == 0:
            return

        logger.debug(f"Updating {len(values)} peers")

        # Prepare the data
        value_dicts = [value.model_dump() for value in values]
        # Prepare the data
        value_dicts = [value.model_dump() for value in values]
        seen: set[tuple[int, int]] = set()
        unique_peers: list[dict[str, Any]] = []

        for value in value_dicts:
            if value["owner_id"] is None or value["id"] is None:
                logger.debug(f"Invalid owner_id or id: {value}")
                continue

            key = (value["owner_id"], value["id"])
            if key not in seen:
                seen.add(key)
                unique_peers.append(value)

        # Create insert statement with ON CONFLICT
        insert_statement = pg_insert(cls).values(unique_peers)

        # Update all fields on conflict
        upsert_statement = insert_statement.on_conflict_do_update(
            index_elements=["owner_id", "id"],  # The composite key columns
            set_={
                "access_hash": insert_statement.excluded.access_hash,
                "type": insert_statement.excluded.type,
                "phone_number": insert_statement.excluded.phone_number,
                "last_update_on": insert_statement.excluded.last_update_on,
            },
        )

        await session.execute(upsert_statement)
        await session.commit()


class TelegramUsernames(SQLModel, table=True):
    __tablename__ = "telegram_usernames"  # type: ignore
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id"],
            ["telegram_sessions.owner_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["owner_id", "id"],
            ["telegram_peers.owner_id", "telegram_peers.id"],
            ondelete="CASCADE",
        ),
        PrimaryKeyConstraint("owner_id", "id", name="telegram_usernames_pkey"),
    )

    owner_id: int = Field(sa_type=BigInteger)
    id: int = Field(sa_type=BigInteger, index=True)
    username: str = Field(sa_type=String, index=True)

    @classmethod
    async def delete_many(
        cls, owner_id: int, values: list[int], session: AsyncSession
    ) -> None:
        statement = delete(cls).where(
            col(cls.owner_id) == owner_id, col(cls.id).in_(values)
        )
        await session.execute(statement)

    @classmethod
    async def update_many(
        cls, values: list["TelegramUsernames"], session: AsyncSession
    ) -> None:
        assert values is not None, "Values is None"
        if len(values) == 0:
            return

        logger.debug(f"Updating {len(values)} usernames")

        # Prepare the data
        value_dicts = [value.model_dump() for value in values]
        seen: set[tuple[int, int]] = set()
        unique_usernames: list[dict[str, Any]] = []

        for value in value_dicts:
            if value["owner_id"] is None or value["id"] is None:
                logger.debug(f"Invalid owner_id or id: {value}")
                continue

            key = (value["owner_id"], value["id"])
            if key not in seen:
                seen.add(key)
                unique_usernames.append(value)

        # Create insert statement with ON CONFLICT
        insert_statement = pg_insert(cls).values(unique_usernames)

        # Option 1: Update all fields on conflict
        upsert_statement = insert_statement.on_conflict_do_update(
            index_elements=["owner_id", "id"],  # The composite key columns
            set_={
                "username": insert_statement.excluded.username,
            },
        )

        await session.execute(upsert_statement)
        await session.commit()


class TelegramUpdateState(SQLModel, table=True):
    __tablename__ = "telegram_update_state"  # type: ignore
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id"],
            ["telegram_sessions.owner_id"],
            ondelete="CASCADE",
        ),
    )

    owner_id: int = Field(sa_type=BigInteger, primary_key=True)
    id: int = Field(sa_type=BigInteger, primary_key=True)
    pts: int = Field(sa_type=BigInteger)
    qts: int = Field(sa_type=BigInteger)
    date: int = Field(
        sa_type=BigInteger,
        nullable=False,
        default_factory=lambda: int(datetime.now().timestamp()),
    )
    seq: int = Field(sa_type=BigInteger)

    @classmethod
    async def update_many(
        cls, values: list["TelegramUpdateState"], session: AsyncSession
    ) -> None:
        assert values is not None, "Values is None"

        if len(values) == 0:
            return

        logger.debug(f"Updating {len(values)} update states")

        # Prepare the data
        value_dicts = [value.model_dump() for value in values]

        # Create insert statement with ON CONFLICT
        insert_statement = pg_insert(cls).values(value_dicts)

        upsert_statement = insert_statement.on_conflict_do_update(
            index_elements=["owner_id", "id"],  # The composite key columns
            set_={
                "pts": insert_statement.excluded.pts,
                "qts": insert_statement.excluded.qts,
                "date": insert_statement.excluded.date,
                "seq": insert_statement.excluded.seq,
            },
        )
        await session.execute(upsert_statement)

        await session.commit()

    @classmethod
    async def fetch_all(
        cls, owner_id: int, session: AsyncSession
    ) -> list["TelegramUpdateState"]:
        statement = (
            select(cls)
            .where(col(cls.owner_id) == owner_id)
            .order_by(col(cls.date).asc())
        )
        result = await session.execute(statement)
        return result.scalars().all()  # type: ignore

    @classmethod
    async def delete(cls, owner_id: int, value: int, session: AsyncSession) -> None:
        statement = delete(cls).where(
            col(cls.owner_id) == owner_id, col(cls.id) == value
        )
        await session.execute(statement)

    @classmethod
    async def replace(
        cls, owner_id: int, value: "TelegramUpdateState", session: AsyncSession
    ) -> None:
        statement = insert(cls).values(
            owner_id=owner_id,
            id=value.id,
            pts=value.pts,
            qts=value.qts,
            date=value.date,
            seq=value.seq,
        )
        await session.execute(statement)


class TelegramVersion(SQLModel, table=True):
    __tablename__ = "telegram_version"  # type: ignore

    number: int = Field(sa_type=BigInteger, primary_key=True)

    @classmethod
    async def insert(cls, value: int, session: AsyncSession) -> None:
        await session.execute(insert(cls).values(number=value))

    @classmethod
    async def get_number(cls, session: AsyncSession) -> int:
        statement = select(cls).order_by(col(cls.number).desc()).limit(1)
        result = await session.execute(statement)
        return result.scalar_one_or_none()  # type: ignore

    @classmethod
    async def set_number(cls, value: int, session: AsyncSession) -> None:
        await session.execute(update(cls).values(number=value))
