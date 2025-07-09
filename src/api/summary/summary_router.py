import random
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from src.api.summary.summary_constants import BATCH_SIZE
from src.api.summary.summary_schemas import (
    ChatSummary,
    ChatSummaryResponse,
    ChatSummaryTopic,
    ChatTypes,
    MarkAsReadRequest,
)
from src.api.summary.summary_service import get_chats_for_summaries
from src.shared.database import Database
from src.shared.dependencies import (
    TelegramLoginParams,
    get_database,
    verify_telegram_auth,
)
from src.telegram.user.summary.summary_schemas import ChatSummary as TelegramChatSummary
from src.telegram.user.summary.summary_schemas import TelegramEntity
from src.telegram.user.summary.summary_service import SummaryService
from src.telegram.user.telegram_session_manager import UserSessionFactory

router = APIRouter()


@router.get("/", response_model=ChatSummaryResponse)
async def get_chat_summary(
    background_tasks: BackgroundTasks,
    # params: Annotated[TelegramLoginParams, Depends(verify_telegram_auth)],
    db: Annotated[Database, Depends(get_database)],
    offset: int = Query(0, description="Number of summaries already returned"),
) -> ChatSummaryResponse:
    """
    Get chat summaries with lazy loading.
    Initial request returns 2 summaries and starts processing more.
    Subsequent requests return pre-processed summaries.
    """
    owner_id = 714862471
    pictures = ["https://github.com/shadcn.png", "https://github.com/leerob.png"]

    async with db.session() as session:
        # Get total unread chats count, sorted by least messages first
        all_entities = await get_chats_for_summaries(owner_id, session)


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
