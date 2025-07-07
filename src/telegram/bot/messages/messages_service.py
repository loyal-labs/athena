import logging
from typing import cast

from pyrogram.client import Client
from pyrogram.types import ForceReply, Message

from src.shared.base import BaseService
from src.telegram.bot.messages.messages_agent import run_response_agent
from src.telegram.bot.messages.messages_schemas import GramMessage, ResponseDependencies

logger = logging.getLogger("athena.telegram.messages.service")


class MessagesService(BaseService):
    @classmethod
    async def respond_to_message(cls, client: Client, og_message: Message) -> None:
        try:
            logger.debug("Checking asserts")
            assert og_message.chat
            assert og_message.from_user
            assert og_message.text
        except AssertionError:
            logger.error(
                "Message %s has no chat or chat username",
                og_message.id,
            )
            await og_message.reply_text("Error: Message has no chat or chat username")  # type: ignore
            return

        chat_peer = og_message.chat.username or og_message.chat.id
        chat_peer = cast(int | str, chat_peer)

        await client.get_chat(chat_peer)

        message_id = og_message.id
        # fetch 20 last messages from the chat
        message_ids = [message_id - i for i in range(5)]
        logger.debug("Fetching messages with ids: %s", message_ids)
        messages = await client.get_messages(chat_peer, message_ids=message_ids)

        # info
        sender = og_message.from_user.first_name
        query = og_message.text

        gram_messages: list[GramMessage] = []
        if messages and isinstance(messages, list):
            logger.debug("Creating GramMessages from pyrogram messages")
            for message in messages:
                try:
                    gram_messages.append(GramMessage.from_pyrogram_message(message))
                except Exception as e:
                    logger.warning(
                        "Error creating GramMessage from pyrogram messages, %s",
                        e,
                    )
                    continue

        logger.debug("Creating ResponseDependencies")
        deps = ResponseDependencies(
            last_messages=gram_messages,
            sender=sender,
            message=og_message,
        )
        logger.debug("Starting response agent")
        response = await run_response_agent(query, deps)
        logger.debug("Response agent finished")

        logger.debug("Sending response to message %s", og_message.id)
        await og_message.reply_text(  # type: ignore
            response,
            reply_markup=ForceReply(selective=True),
        )
        logger.debug("Response sent to message %s", og_message.id)
        return
