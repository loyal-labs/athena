import logging

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types import Message

from src.shared.database import Database, DatabaseFactory
from src.telegram.user.summary.summary_schemas import ChatMessage, TelegramEntity

logger = logging.getLogger("athena.telegram.user.summary.handlers")


class SummaryHandlers:
    async def __get_telegram_entity(
        self, client: Client, message: Message
    ) -> TelegramEntity:
        database = await DatabaseFactory.get_instance()

        assert client.me is not None, "Client is not authenticated"
        assert message.chat is not None, "Message chat is None"
        assert message.chat.id is not None, "Message chat ID is None"
        assert database is not None, "Database is None"
        assert isinstance(database, Database), "Database is not a Database instance"

        owner_id = client.me.id
        chat_id = message.chat.id

        async with database.session() as session:
            telegram_entity = await TelegramEntity.get(owner_id, chat_id, session)

            if telegram_entity is None:
                logger.debug("Telegram entity not found for chat %s", chat_id)
                chat = await client.get_chat(chat_id)
                telegram_entity = TelegramEntity.from_chat(chat, message, owner_id)

                # TODO: connect to the database
                # await telegram_entity.insert(session)
                logger.debug("Telegram entity created for chat %s", chat_id)

            return telegram_entity

    async def incoming_message(self, client: Client, message: Message) -> None:
        assert message.chat is not None, "Message chat is None"
        assert message.chat.id is not None, "Message chat ID is None"
        assert client.me is not None, "Client is not authenticated"
        assert client.me.id is not None, "Client ID is None"

        telegram_entity = await self.__get_telegram_entity(client, message)

        chat_message = ChatMessage.extract_chat_message_info(
            message, telegram_entity.owner_id, telegram_entity.chat_id
        )

        # TODO: connect to the database
        # await chat_message.insert(session)
        logger.debug("Chat message created for chat %s", telegram_entity.chat_id)

    @property
    def summary_handlers(self) -> list[Handler]:
        return [
            MessageHandler(
                self.incoming_message,
                filters.incoming | filters.me,
            ),
        ]
