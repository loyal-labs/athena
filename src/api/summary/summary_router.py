import random
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.api.summary.summary_schemas import (
    ChatSummary,
    ChatSummaryTopic,
    ChatTypes,
    MarkAsReadRequest,
)
from src.shared.database import Database
from src.shared.dependencies import (
    TelegramLoginParams,
    get_database,
    verify_telegram_auth,
)
from src.telegram.user.summary.summary_schemas import ChatSummary as TelegramChatSummary
from src.telegram.user.summary.summary_service import SummaryService
from src.telegram.user.telegram_session_manager import UserSessionFactory

router = APIRouter()


@router.get("/", response_model=list[ChatSummary])
async def get_chat_summary(
    params: Annotated[TelegramLoginParams, Depends(verify_telegram_auth)],
    db: Annotated[Database, Depends(get_database)],
) -> list[ChatSummary]:
    """
    Get the chat summary for the current user.
    """
    owner_id = int(params.id)
    pictures = ["https://github.com/shadcn.png", "https://github.com/leerob.png"]

    async with db.session() as session:
        # Fetch summaries from database
        db_summaries = await TelegramChatSummary.get_all_for_owner(owner_id, session)

        # Transform to API response format
        api_summaries: list[ChatSummary] = []
        for db_summary in db_summaries:
            selected_picture = random.choice(pictures)
            # Transform topics to API format
            api_topics: list[ChatSummaryTopic] = []
            for topic in db_summary.topics:
                api_topics.append(
                    ChatSummaryTopic(
                        topic=topic["topic"],
                        date=topic["date"],
                        points=topic["points"],  # Already in correct format
                    )
                )

            api_summaries.append(
                ChatSummary(
                    name=db_summary.name,
                    profile_picture=selected_picture,
                    chat_type=ChatTypes.from_telegram_type(db_summary.chat_type),
                    topics=api_topics,
                )
            )

        return api_summaries


@router.post("/read")
async def mark_as_read(
    request: MarkAsReadRequest,
    params: Annotated[TelegramLoginParams, Depends(verify_telegram_auth)],
    db: Annotated[Database, Depends(get_database)],
) -> None:
    """
    Mark a chat as read.
    """
    owner_id = int(params.id)
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
