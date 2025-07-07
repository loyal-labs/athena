import logging

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.enums import ChatAction
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types import Message

from src.telegram.bot.messages.messages_service import MessagesService

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
        ]
