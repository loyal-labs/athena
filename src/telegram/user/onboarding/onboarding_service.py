import logging
import time
from datetime import datetime

import pandas as pd
from pyrogram.client import Client
from pyrogram.enums import ChatAction, ParseMode
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.base import BaseService
from src.shared.database import DatabaseFactory
from src.telegram.bot.client.telegram_bot import TelegramBot, TelegramBotFactory
from src.telegram.user.login.login_schemas import LoginSession
from src.telegram.user.summary.summary_schemas import TelegramEntity
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
                user_client_object = await session_manager.get_or_create_session(
                    owner_id, db_session
                )
                user_client = user_client_object.get_client()

                # Step 1: Send welcome message
                await self._send_welcome_message(bot, owner_id)

                # Step 2: Analyze interests
                interests = await self._analyze_interests(
                    user_client, summary_service, db_session
                )

                # Step 3: Send personalized message based on interests
                await self._send_interest_message(bot_client, owner_id, interests)

                # Mark user as onboarded
                return await self._mark_as_onboarded(owner_id, db_session)

        except Exception as e:
            logger.error(f"Error during onboarding for user {owner_id}: {e}")
            raise e

    async def _send_welcome_message(self, bot: TelegramBot, owner_id: int) -> None:
        """Send initial welcome message."""
        client = bot.get_client()

        message_1 = """
hi! it's a pleasure to meet you! 
        """

        message_2 = """
bear with me, i need a minute to go over your chats to grasp your interests and the best way I can help you.
        """

        blog_link = (
            "https://telegra.ph/Welcome-Let-me-tell-you-a-bit-about-myself-07-08"
        )
        blog_hyperlink = f"<a href='{blog_link}'>\u200b</a>"
        message_3 = f"""
here's something i prepared for you while you're waiting. it's a short gist of who i am and things i can do!

hope you like it {blog_hyperlink} 👉🏻👈🏻 
        """

        message_4 = """
ok, let me get back to your messages though. i'll be back in a second.
        """

        await client.send_chat_action(owner_id, ChatAction.TYPING)
        time.sleep(0.25)
        await client.send_message(owner_id, message_1)
        await client.send_chat_action(owner_id, ChatAction.TYPING)
        time.sleep(2)

        await client.send_message(owner_id, message_2)
        await client.send_chat_action(owner_id, ChatAction.TYPING)
        time.sleep(4)

        await client.send_message(owner_id, message_3)
        time.sleep(1)
        await client.send_message(owner_id, message_4)
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
        login_sessions = await LoginSession.get_by_owner(owner_id, db_session)
        for session in login_sessions:
            session.is_onboarded = True
            session.updated_at = datetime.now()

        await db_session.commit()

        return True
