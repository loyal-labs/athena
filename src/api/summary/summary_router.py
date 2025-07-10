import asyncio
import logging
import random
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from src.api.summary.summary_constants import STEP
from src.api.summary.summary_resp import (
    ChatSummary,
    ChatSummaryPoint,
    ChatSummaryResponse,
    ChatSummaryTopic,
    ChatTypes,
)
from src.shared.database import Database, DatabaseFactory
from src.shared.dependencies import (
    TelegramLoginParams,
    get_database,
    get_summary_service,
    get_user_session_manager,
    verify_telegram_auth,
)
from src.telegram.user.summary.summary_schemas import (
    TelegramChatSummary as TelegramChatSummary,
)
from src.telegram.user.summary.summary_schemas import TelegramMessage
from src.telegram.user.summary.summary_service import SummaryService
from src.telegram.user.telegram_session_manager import UserSessionManager

router = APIRouter()

logger = logging.getLogger("src.api.summary.summary_router")


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


@router.get("/read")
async def mark_as_read(
    # params: Annotated[TelegramLoginParams, Depends(verify_telegram_auth)],
    summary_service: Annotated[SummaryService, Depends(get_summary_service)],
    session_manager: Annotated[UserSessionManager, Depends(get_user_session_manager)],
    db: Annotated[Database, Depends(get_database)],
    chat_id: int = Query(..., description="Chat ID"),
    max_id: int = Query(..., description="Max ID"),
) -> JSONResponse:
    """
    Mark a chat as read.
    """
    owner_id = 714862471

    try:
        async with db.session() as session:
            user_client_object = await session_manager.get_or_create_session(
                owner_id, session
            )
            user_client = user_client_object.get_client()

            db_job = TelegramMessage.mark_as_read(session, owner_id, chat_id, max_id)
            tg_job = summary_service.mark_as_read(user_client, chat_id, max_id)

            await asyncio.gather(db_job, tg_job)

        return JSONResponse(
            status_code=200,
            content={"message": "Success"},
        )
    except Exception as e:
        logger.error(f"Error marking chat as read: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
