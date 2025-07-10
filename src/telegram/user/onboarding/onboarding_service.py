import asyncio
import logging
import time

import pandas as pd
from pyrogram.client import Client
from pyrogram.enums import ChatAction, ParseMode
from pyrogram.raw.functions.messages.toggle_dialog_pin import ToggleDialogPin
from pyrogram.raw.types.input_dialog_peer import InputDialogPeer
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

        assert bot_client.me is not None
        assert bot_client.me.username is not None

        bot_id = bot_client.me.id

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

                # Step 3: Send personalized message
                logger.debug(f"Sending personalized message to user {owner_id}")
                await self._send_interest_message(bot_client, owner_id, interests)

            async with db_session as session:
                logger.debug(f"Downloading unread chats for user {owner_id}")
                await self.__download_unread_chats(
                    user_client, owner_id, summary_service, session
                )
                logger.debug(f"Downloaded unread chats for user {owner_id}")
                await self.__insert_empty_chat_summaries(owner_id, db_session)

                # Step 4: Pin the bot and mark as is_pinned and onboarded
                await self._pin_bot(user_client, bot_id)
                await self._mark_as_onboarded(owner_id, db_session)
                logger.debug(f"Marking user {owner_id} as onboarded")

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
        for chat in chats:
            print(chat.title)

        total_chats = len(chats)
        for idx, chat in enumerate(chats):
            print(f"{chat.chat_id} {chat.title}")
            logger.debug(f"Downloading messages for step {idx + 1}/{total_chats}")

            result = await summary_service.get_unread_messages_from_chat(client, chat)
            await TelegramMessage.insert_many(result, db_session, commit=False)
            logger.debug(f"Inserted {len(result)} messages for chat {chat.title}")

        await db_session.commit()

    async def __insert_empty_chat_summaries(
        self, owner_id: int, db_session: AsyncSession
    ) -> None:
        """Insert empty chat summaries for all unread chats."""
        unique_chat_ids = await TelegramMessage.get_unique_chat_ids(
            owner_id, db_session
        )
        await TelegramChatSummary.insert_empty(owner_id, unique_chat_ids, db_session)

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

    async def _mark_as_onboarded(self, owner_id: int, db_session: AsyncSession) -> None:
        """Mark the user as onboarded in the database."""
        await OnboardingSchema.mark_as_onboarded(owner_id, db_session)

    async def _pin_bot(
        self,
        user_client: Client,
        peer_id: int,
    ) -> None:
        try:
            peer = await user_client.resolve_peer(peer_id)  # Get the peer

            dialog_peer = InputDialogPeer(peer=peer)  # type: ignore

            await user_client.invoke(
                ToggleDialogPin(
                    peer=dialog_peer,  # type: ignore
                    pinned=True,
                )
            )

        except Exception as e:
            logger.error(f"Error pinning bot {peer_id}: {e}")
            raise e
