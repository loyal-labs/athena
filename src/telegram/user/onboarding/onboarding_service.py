import asyncio
import logging
import time

import pandas as pd
from pyrogram.client import Client
from pyrogram.enums import ChatAction, ParseMode
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.base import BaseService
from src.shared.database import DatabaseFactory
from src.telegram.bot.client.telegram_bot import TelegramBot, TelegramBotFactory
from src.telegram.user.onboarding.onboarding_schemas import OnboardingSchema
from src.telegram.user.onboarding.onboarding_texts import (
    WELCOME_MESSAGE_1,
    WELCOME_MESSAGE_2,
    WELCOME_MESSAGE_3,
    WELCOME_MESSAGE_4,
)
from src.telegram.user.summary.summary_schemas import (
    TelegramChatSummary,
    TelegramEntity,
    TelegramMessage,
)
from src.telegram.user.summary.summary_service import SummaryService
from src.telegram.user.telegram_session_manager import UserSessionFactory

logger = logging.getLogger("athena.telegram.user.onboarding")


class OnboardingService(BaseService):
    """
    Handles new user onboarding by:
    1. Detecting first-time users
    2. Parsing their chats
    3. Analyzing interests
    4. Sending welcome messages
    """

    async def run_onboarding_pipeline(self, owner_id: int) -> bool:
        """Run the complete onboarding pipeline for a new user."""
        bot = await TelegramBotFactory.get_instance()
        bot_client = bot.get_client()
        summary_service = SummaryService()
        try:
            # Get user session
            session_manager = await UserSessionFactory.get_instance()
            database = await DatabaseFactory.get_instance()

            async with database.session() as db_session:
                logger.debug(f"Getting or creating session for user {owner_id}")
                user_client_object = await session_manager.get_or_create_session(
                    owner_id, db_session
                )
                user_client = user_client_object.get_client()

                logger.debug(f"Sending welcome message to user {owner_id}")
                # Step 1: Send welcome message
                welcome_message_task = self._send_welcome_message(bot, owner_id)

                # Step 2: Analyze interests
                logger.debug(f"Analyzing interests for user {owner_id}")
                interests_task = self._analyze_interests(
                    user_client, summary_service, db_session
                )

                _, interests = await asyncio.gather(
                    welcome_message_task, interests_task
                )
                logger.debug(f"Interests analyzed for user {owner_id}")

                logger.debug(f"Sending personalized message to user {owner_id}")
                jobs = [
                    # Step 3: Send personalized message based on interests
                    self._send_interest_message(bot_client, owner_id, interests),
                    # Step 4: Download the first unread chats
                    self.__insert_empty_chat_summaries(owner_id, db_session),
                ]

                await asyncio.gather(*jobs)

                # Mark user as onboarded
                logger.debug(f"Marking user {owner_id} as onboarded")
                await self._mark_as_onboarded(owner_id, db_session)

            async with db_session as session:
                logger.debug(f"Downloading unread chats for user {owner_id}")
                await self.__download_unread_chats(
                    user_client, owner_id, summary_service, session
                )
                logger.debug(f"Downloaded unread chats for user {owner_id}")

            return True

        except Exception as e:
            logger.error(f"Error during onboarding for user {owner_id}: {e}")
            raise e

    async def __download_unread_chats(
        self,
        client: Client,
        owner_id: int,
        summary_service: SummaryService,
        db_session: AsyncSession,
    ) -> None:
        """Download the first unread chats for a user."""
        chats = await TelegramEntity.get_unread(owner_id, db_session)

        for i in range(0, len(chats), 2):
            messages: list[TelegramMessage] = []
            chat_chunk = chats[i : i + 2]
            tasks = [
                summary_service.get_unread_messages_from_chat(client, chat.chat_id)
                for chat in chat_chunk
            ]
            if tasks:
                logger.debug(
                    f"Downloading messages for {len(tasks)} chats concurrently."
                )
                results_list = await asyncio.gather(*tasks)
                for result in results_list:
                    if result:
                        messages.extend(result)
            await TelegramMessage.insert_many(messages, db_session, commit=False)
            logger.debug(f"Inserted {len(messages)} messages for chat {i}")

        await db_session.commit()

    async def __insert_empty_chat_summaries(
        self, owner_id: int, db_session: AsyncSession
    ) -> None:
        """Insert empty chat summaries for all unread chats."""
        chats = await TelegramEntity.get_unread(owner_id, db_session)
        await TelegramChatSummary.insert_empty(chats, db_session)

    async def _send_welcome_message(self, bot: TelegramBot, owner_id: int) -> None:
        """Send initial welcome message."""
        client = bot.get_client()

        await client.send_chat_action(owner_id, ChatAction.TYPING)
        time.sleep(0.25)
        await client.send_message(owner_id, WELCOME_MESSAGE_1)
        await client.send_chat_action(owner_id, ChatAction.TYPING)
        time.sleep(2)

        await client.send_message(owner_id, WELCOME_MESSAGE_2)
        await client.send_chat_action(owner_id, ChatAction.TYPING)
        time.sleep(4)

        await client.send_message(owner_id, WELCOME_MESSAGE_3)
        time.sleep(1)
        await client.send_message(owner_id, WELCOME_MESSAGE_4)
        await client.send_chat_action(owner_id, ChatAction.TYPING)

    async def _analyze_interests(
        self,
        client: Client,
        summary_service: SummaryService,
        db_session: AsyncSession,
    ) -> pd.DataFrame:
        """Analyze user interests based on their chats and store them."""
        chats = await summary_service.isolate_interests(client)

        # Conver to the list of dictionaries
        chats_array_dict = chats.to_dict(orient="records")  # type: ignore
        chats_entities = [
            TelegramEntity.model_validate(chat) for chat in chats_array_dict
        ]
        # Store in the database
        await TelegramEntity.insert_many(chats_entities, db_session)
        return chats

    async def _send_interest_message(
        self,
        bot_client: Client,
        owner_id: int,
        interests: pd.DataFrame,
    ) -> None:
        """Send personalized message based on user interests."""
        total_chats = len(interests)
        groups = interests[interests["chat_type"] == "GROUP"].shape[0]
        channels = interests[interests["chat_type"] == "CHANNEL"].shape[0]
        private = interests[interests["chat_type"] == "PRIVATE"].shape[0]

        message = f"""
✨ <b>Your Telegram Analysis</b>

        📊 Total chats of interest: {total_chats}
        👥 Groups of interest: {groups}
        📢 Channels of interest: {channels}
        💬 Private chats of interest: {private}

🔥 <b>Your Most Active Chats:</b>"""
        most_active_chats = interests.head(5)
        position = 1
        for _, chat in most_active_chats.iterrows():  # type: ignore
            chat_title = chat["title"]  # type: ignore
            rating = chat["rating"]  # type: ignore

            username = chat["username"]  # type: ignore

            if username:
                chat_title = f"<a href='https://t.me/{username}'>{chat_title}</a>"

            message += f"\n{position}. {chat_title} ({rating:.2f} points)"
            position += 1

        message += "\nI'll help you stay on top of important conversations!"

        await bot_client.send_message(owner_id, message, parse_mode=ParseMode.HTML)

    async def _mark_as_onboarded(self, owner_id: int, db_session: AsyncSession) -> bool:
        """Mark the user as onboarded in the database."""
        await OnboardingSchema.mark_as_onboarded(owner_id, db_session)
        return True
