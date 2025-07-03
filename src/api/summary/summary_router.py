import random

from fastapi import APIRouter

from src.api.summary.summary_schemas import ChatSummary, ChatSummaryTopic, ChatTypes
from src.shared.database import DatabaseFactory
from src.telegram.user.summary.summary_schemas import ChatSummary as TelegramChatSummary

router = APIRouter()


@router.get("/", response_model=list[ChatSummary])
async def get_chat_summary() -> list[ChatSummary]:
    """
    Get the chat summary for the current user.
    """
    owner_id = 714862471  # TODO: Get from auth/session
    pictures = ["https://github.com/shadcn.png", "https://github.com/leerob.png"]
    db = await DatabaseFactory.get_instance()

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
