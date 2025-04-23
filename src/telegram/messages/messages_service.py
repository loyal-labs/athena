import logging
from typing import cast

from pyrogram.types import ForceReply

from src.shared.base import BaseService
from src.shared.event_bus import Event, EventBus
from src.shared.event_registry import MessageTopics
from src.telegram.messages.messages_agent import run_decision_agent
from src.telegram.messages.messages_schemas import (
    GramMessage,
    RespondToMessagePayload,
    ResponseDependencies,
)

logger = logging.getLogger("athena.telegram.messages")


class MessagesService(BaseService):
    def __init__(self, event_bus: EventBus):
        super().__init__()
        self.event_bus = event_bus

    @EventBus.subscribe(MessageTopics.RESPOND_TO_MESSAGE)
    async def respond_to_message(self, event: Event) -> None:
        logger.debug("Responding to message: %s", event.payload)
        payload = cast(
            RespondToMessagePayload,
            event.extract_payload(event, RespondToMessagePayload),
        )
        client = payload.client
        message = payload.message

        try:
            logger.debug("Checking asserts")
            assert message.chat
            assert message.chat.username
            assert message.from_user
            assert message.text
        except AssertionError:
            logger.error(
                "Message %s has no chat or chat username",
                message.id,
            )
            await message.reply_text("Error: Message has no chat or chat username")  # type: ignore
            return

        chat_username = message.chat.username
        await client.get_chat(chat_username)

        message_id = message.id
        # fetch 20 last messages from the chat
        message_ids = [message_id - i for i in range(20)]
        logger.debug("Fetching messages with ids: %s", message_ids)
        messages = await client.get_messages(chat_username, message_ids=message_ids)

        # info
        sender = message.from_user.first_name
        query = message.text

        gram_messages: list[GramMessage] = []
        if messages and isinstance(messages, list):
            logger.debug("Creating GramMessages from pyrogram messages")
            for message in messages:
                try:
                    gram_messages.append(GramMessage.from_pyrogram_message(message))
                except Exception as e:
                    logger.exception(
                        "Error creating GramMessage from pyrogram messages, %s",
                        e,
                    )
                    continue

        logger.debug("Creating ResponseDependencies")
        deps = ResponseDependencies(
            last_messages=gram_messages,
            event_bus=self.event_bus,
            sender=sender,
            message=message,
        )
        logger.debug("Starting response agent")
        response = await self.start_response_agent(query, deps)
        logger.debug("Response agent finished")

        logger.debug("Sending response to message %s", message.id)
        await message.reply_text(  # type: ignore
            response,
            reply_markup=ForceReply(selective=True),
        )
        logger.debug("Response sent to message %s", message.id)
        return

    async def start_response_agent(self, query: str, deps: ResponseDependencies) -> str:
        response = await run_decision_agent(query, deps)
        return response
