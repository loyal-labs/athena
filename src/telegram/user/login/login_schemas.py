from datetime import datetime
from logging import getLogger
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, Relationship, SQLModel, select

if TYPE_CHECKING:
    from src.telegram.user.summary.summary_schemas import TelegramEntity

logger = getLogger("telegram.user.login.login_schemas")


class LoginSession(SQLModel, table=True):
    __tablename__ = "login_sessions"  # type: ignore

    owner_id: int = Field(sa_type=BigInteger, primary_key=True)
    session_string: str = Field(sa_type=String, primary_key=True)
    created_at: datetime = Field(sa_type=DateTime, default_factory=datetime.now)
    updated_at: datetime = Field(sa_type=DateTime, default_factory=datetime.now)

    # Relationship to TelegramEntity
    telegram_entities: list["TelegramEntity"] = Relationship(
        back_populates="login_session",
        sa_relationship_kwargs={"lazy": "select", "cascade": "all, delete-orphan"},
    )

    @classmethod
    async def get(
        cls, owner_id: int, session_string: str, session: AsyncSession
    ) -> "LoginSession | None":
        """Get a LoginSession by owner_id and session_string."""
        result = await session.execute(
            select(cls).where(
                cls.owner_id == owner_id, cls.session_string == session_string
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_by_owner(
        cls, owner_id: int, session: AsyncSession
    ) -> list["LoginSession"]:
        """Get all LoginSessions for a specific owner."""
        result = await session.execute(select(cls).where(cls.owner_id == owner_id))
        return list(result.scalars().all())

    async def insert(self, session: AsyncSession) -> "LoginSession":
        """Insert a single LoginSession into the database."""
        session.add(self)
        await session.commit()
        await session.refresh(self)
        return self

    @classmethod
    async def get_or_create(
        cls, owner_id: int, session_string: str, session: AsyncSession
    ) -> tuple["LoginSession", bool]:
        """Get an existing LoginSession or create a new one. Returns (instance, created)."""
        existing = await cls.get(owner_id, session_string, session)
        if existing:
            return existing, False

        new_session = cls(owner_id=owner_id, session_string=session_string)
        await new_session.insert(session)
        return new_session, True
