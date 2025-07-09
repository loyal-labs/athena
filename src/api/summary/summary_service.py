from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.telegram.user.summary.summary_schemas import TelegramEntity


async def get_chats_for_summaries(
    owner_id: int, session: AsyncSession
) -> list[TelegramEntity]:
    stmt = (
        select(TelegramEntity)
        .where(
            TelegramEntity.owner_id == owner_id,
            TelegramEntity.chat_type != "CHANNEL",
            TelegramEntity.unread_count > 0,
            TelegramEntity.rating > 0.1,
        )
        .order_by(TelegramEntity.unread_count.asc())  # type: ignore
    )

    result = await session.execute(stmt)
    return list(result.scalars().all())
