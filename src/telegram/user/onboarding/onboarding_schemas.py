from datetime import datetime
from logging import getLogger

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKeyConstraint, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel, select

logger = getLogger("telegram.user.onboarding.login_schemas")


class OnboardingSchema(SQLModel, table=True):
    __tablename__ = "user_onboarding"  # type: ignore
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id"],
            ["telegram_sessions.owner_id"],
            ondelete="CASCADE",
        ),
    )

    owner_id: int = Field(sa_type=BigInteger, primary_key=True, unique=True)
    is_onboarded: bool = Field(sa_type=Boolean)
    created_at: datetime = Field(
        sa_type=DateTime,
        nullable=False,
        default_factory=lambda: datetime.now(),
    )
    updated_at: datetime = Field(
        sa_type=DateTime,
        nullable=False,
        default_factory=lambda: datetime.now(),
    )

    @classmethod
    async def create(cls, owner_id: int, session: AsyncSession) -> None:
        stmt = select(cls).where(cls.owner_id == owner_id)
        result = await session.execute(stmt)

        fetched_result = result.scalar_one_or_none()
        if fetched_result is not None:
            return

        stmt = insert(cls).values(owner_id=owner_id, is_onboarded=False)
        await session.execute(stmt)
        await session.commit()

    @classmethod
    async def get(cls, owner_id: int, session: AsyncSession) -> "OnboardingSchema":
        stmt = select(cls).where(cls.owner_id == owner_id)
        result = await session.execute(stmt)
        fetched_result = result.scalar_one_or_none()

        assert fetched_result is not None, "Onboarding status not found"

        return fetched_result

    @classmethod
    async def mark_as_onboarded(cls, owner_id: int, session: AsyncSession) -> None:
        stmt = select(cls).where(cls.owner_id == owner_id)
        result = await session.execute(stmt)
        fetched_result = result.scalar_one_or_none()

        assert fetched_result is not None, "Onboarding status not found"

        fetched_result.is_onboarded = True
        fetched_result.updated_at = datetime.now()
        await session.commit()
        await session.refresh(fetched_result)
