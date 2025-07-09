import logging

import orjson
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.enums import ChatAction
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types import Message

from src.shared.database import DatabaseFactory
from src.telegram.bot.messages.messages_service import MessagesService
from src.telegram.user.onboarding.onboarding_schemas import OnboardingSchema
from src.telegram.user.onboarding.onboarding_service import OnboardingService
from src.telegram.user.telegram_session_manager import UserSessionFactory

logger = logging.getLogger("athena.telegram.messages.handlers")


class MessageHandlers:
    """
    Message handlers class
    """

    @staticmethod
    async def start_message(client: Client, message: Message) -> Message:
        response = await message.reply_text("Hello, world!")  # type: ignore
        return response

    @staticmethod
    async def login_command(client: Client, message: Message) -> None:
        assert message.from_user is not None, "From user is None"
        assert message.from_user.id is not None, "From user ID is None"
        assert message.text is not None, "Text is None"

        text = message.text.split("/login")[1]
        text_dict = orjson.loads(text.strip().encode("utf-8"))
        dc_id = text_dict.get("dcId")
        auth_key = text_dict.get("authKeyHex")

        assert dc_id, "DC ID is None"
        assert auth_key, "Auth key is None"

        auth_key = bytes.fromhex(auth_key)
        user_session_manager = await UserSessionFactory.get_instance()
        database = await DatabaseFactory.get_instance()

        async with database.session() as db_session:
            await user_session_manager.create_new_session(
                owner_id=message.from_user.id,
                dc_id=dc_id,
                auth_key=auth_key,
                db_session=db_session,
            )

            # Check if first-time user and run onboarding
            onboarding_status = await OnboardingSchema.get(
                message.from_user.id, db_session
            )

            if onboarding_status and not onboarding_status.is_onboarded:
                onboarding = OnboardingService()
                await onboarding.run_onboarding_pipeline(message.from_user.id)

    @staticmethod
    async def help_message(client: Client, message: Message) -> Message:
        response = await message.reply_text("Help message")  # type: ignore
        return response

    @staticmethod
    async def to_athena(_, client: Client, message: Message) -> bool:
        try:
            assert message.text
        except AssertionError:
            logger.error("Message %s has no text, in filters", message.id)
            return False

        looking_for = ["@athena_tgbot", "афина", "athena"]

        # condition 1: Athena's mentioned in the beggining of the message
        if any(
            message.text.lower().startswith(looking_for) for looking_for in looking_for
        ):
            return True
        # condition 2: directly mentioned
        elif "@athena_tgbot" in message.text:
            return True

        # condition 3: response to Athena's message
        elif message.reply_to_message:
            try:
                assert message.reply_to_message.from_user
            except AssertionError:
                logger.error("Message %s is not a response to Athena", message.id)
                return False
            return message.reply_to_message.from_user.is_self

        return False

    async def response(
        self,
        client: Client,
        message: Message,
    ) -> None:
        logger.debug("Received message: %s", message.text)
        try:
            assert message.chat
            assert message.chat.id
        except AssertionError:
            logger.error("Message %s has no chat", message.id)
            return

        logger.debug("Received message: %s", message.text)

        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
        await MessagesService.respond_to_message(client, message)

    @property
    def message_handlers(self) -> list[Handler]:
        message_response = filters.create(self.to_athena)  # type: ignore

        return [
            MessageHandler(self.start_message, filters.command("start")),
            MessageHandler(self.help_message, filters.command("help")),
            MessageHandler(
                self.response,
                message_response & filters.incoming,
            ),
            MessageHandler(self.login_command, filters.command("login")),
        ]
