import asyncio
import random
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.summary.summary_constants import STEP
from src.api.summary.summary_resp import (
    ChatSummary,
    ChatSummaryPoint,
    ChatSummaryResponse,
    ChatSummaryTopic,
    ChatTypes,
    MarkAsReadRequest,
)
from src.shared.database import Database, DatabaseFactory
from src.shared.dependencies import (
    TelegramLoginParams,
    get_database,
    get_summary_service,
    verify_telegram_auth,
)
from src.telegram.user.summary.summary_schemas import (
    TelegramChatSummary as TelegramChatSummary,
)
from src.telegram.user.summary.summary_service import SummaryService
from src.telegram.user.telegram_session_manager import UserSessionFactory

router = APIRouter()


@router.get("/", response_model=ChatSummaryResponse)
async def get_chat_summary(
    # params: Annotated[TelegramLoginParams, Depends(verify_telegram_auth)],
    summary_service: Annotated[SummaryService, Depends(get_summary_service)],
    page: int = Query(0, description="Page of the summary"),
) -> ChatSummaryResponse:
    """
    Get chat summaries with lazy loading.
    Initial request returns 2 summaries and starts processing more.
    Subsequent requests return pre-processed summaries.
    """
    db = await DatabaseFactory.get_instance()
    owner_id = 714862471
    pictures = ["https://github.com/shadcn.png", "https://github.com/leerob.png"]

    async with db.session() as session:
        unread_chats = await TelegramChatSummary.count_unread_summaries(
            owner_id, session
        )
        assert unread_chats is not None, "Unread chats are required"
        assert page <= unread_chats, "Page is out of bounds"

        if unread_chats == 0:
            return ChatSummaryResponse(
                step=0,
                total_pages=0,
                page=page,
                chats=[],
            )
        else:
            unread_chats = unread_chats - 1

        chats = await TelegramChatSummary.get_chat_with_offset(owner_id, session, page)

        assert unread_chats is not None, "Unread chats are required"
        assert chats is not None, "Chats are required"
        assert len(chats) == 1, "Only one chat should be returned"

        chat = chats[0]
        chat_id = chat.chat_id
        title = chat.telegram_entity.title or ""
        chat_type = chat.telegram_entity.chat_type or ""
        unread_count = chat.telegram_entity.unread_count

        if chat.topics is None or len(chat.topics) == 0:
            chat = await summary_service.create_chat_summary(
                owner_id,
                chat_id,
                session,
                title,
                chat_type,
                unread_count,
            )
        assert chat is not None, "Chat is required"
        assert chat.topics is not None, "Chat topics are required"

        return ChatSummaryResponse(
            step=STEP,
            total_pages=unread_chats,
            page=page,
            chats=[
                ChatSummary(
                    name=title,
                    profile_picture=random.choice(pictures),
                    chat_type=ChatTypes.from_telegram_type(chat_type),
                    topics=[
                        ChatSummaryTopic(
                            topic=topic["topic"],
                            date=topic["date"],
                            points=[
                                ChatSummaryPoint(
                                    name=point["name"],
                                    profile_picture=random.choice(pictures),
                                    summary=point["summary"],
                                )
                                for point in topic["points"]
                            ],
                        )
                        for topic in chat.topics
                    ],
                )
            ],
        )


@router.post("/read")
async def mark_as_read(
    request: MarkAsReadRequest,
    # params: Annotated[TelegramLoginParams, Depends(verify_telegram_auth)],
    db: Annotated[Database, Depends(get_database)],
) -> None:
    """
    Mark a chat as read.
    """
    owner_id = 714862471
    session_manager = await UserSessionFactory.get_instance()

    async with db.session() as session:
        user_client_object = await session_manager.get_or_create_session(
            owner_id, session
        )

    user_client = user_client_object.get_client()

    try:
        summary_service = SummaryService()
        await summary_service.mark_as_read(user_client, request.chat_id, request.max_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
