import logging

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.enums import ChatType
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types import Message

from src.shared.cache import disk_cache
from src.shared.database import AsyncSession, DatabaseFactory
from src.telegram.user.summary.summary_schemas import TelegramEntity, TelegramMessage

logger = logging.getLogger("athena.telegram.user.summary.handlers")


class TelegramUserMessageHandlers:
    SUPPORTED_CHAT_TYPES = [
        ChatType.PRIVATE,
        ChatType.GROUP,
        ChatType.SUPERGROUP,
        ChatType.CHANNEL,
    ]

    # Cache
    ENTITY_CACHE_TTL = 60 * 30  # 30 minutes

    # Filters
    LOWEST_RATING = 0
    GROUP_HIGH_LIMIT = 200
    SUPERGROUP_HIGH_LIMIT = 200
    GROUP_UNREAD_COUNT_THRESHOLD = 250

    @staticmethod
    @disk_cache(key_params=["owner_id", "chat_id"], ttl=ENTITY_CACHE_TTL)
    async def __get_entity_from_db(
        session: AsyncSession,
        owner_id: int,
        chat_id: int,
    ) -> TelegramEntity | None:
        telegram_entity = await TelegramEntity.get(owner_id, chat_id, session)
        return telegram_entity

    @staticmethod
    @disk_cache(key_params=["owner_id", "chat_id"], ttl=ENTITY_CACHE_TTL)
    async def __get_entity_from_tg(
        client: Client,
        message: Message,
        owner_id: int,
        chat_id: int,
    ) -> TelegramEntity:
        chat = await client.get_chat(chat_id)
        telegram_entity = TelegramEntity.from_chat(chat, message, owner_id)
        return telegram_entity

    @staticmethod
    async def __should_insert_message(
        entity: TelegramEntity,
    ) -> bool:
        logger.debug("New entity encountered: %s", entity)
        if entity.chat_type == "PRIVATE":
            return True

        elif entity.chat_type in ["GROUP", "SUPERGROUP"]:
            # Rating > 0 or (user_count < 200 and unread_count > 250)
            rating_threshold = entity.rating > TelegramUserMessageHandlers.LOWEST_RATING
            user_count_threshold = (
                entity.members_count < TelegramUserMessageHandlers.GROUP_HIGH_LIMIT
            )
            unread_count_threshold = (
                entity.unread_count
                < TelegramUserMessageHandlers.GROUP_UNREAD_COUNT_THRESHOLD
            )
            return rating_threshold or (user_count_threshold and unread_count_threshold)

        elif entity.chat_type == "CHANNEL":
            # Rating > 0
            rating_threshold = entity.rating > TelegramUserMessageHandlers.LOWEST_RATING
            return rating_threshold

        return False

    @staticmethod
    async def __conditional_insert(
        session: AsyncSession,
        client: Client,
        message: Message,
        owner_id: int,
        chat_id: int,
    ) -> bool:
        assert client.me is not None, "Client is not authenticated"
        assert message.chat is not None, "Message chat is None"
        assert message.chat.id is not None, "Message chat ID is None"

        should_insert = True

        try:
            # If the entity was already in db, we selected it, insert
            telegram_entity = await TelegramUserMessageHandlers.__get_entity_from_db(
                session, owner_id, chat_id
            )

            if telegram_entity:
                if isinstance(telegram_entity, dict):
                    telegram_entity = TelegramEntity.from_dict(
                        owner_id, telegram_entity
                    )

                unread_count = telegram_entity.unread_count + 1
                await TelegramEntity.update_unread_count(
                    session, owner_id, chat_id, unread_count, commit=False
                )
            else:
                telegram_entity = (
                    await TelegramUserMessageHandlers.__get_entity_from_tg(
                        client, message, owner_id, chat_id
                    )
                )

                # TODO: find a better way to deal with cache resp
                if isinstance(telegram_entity, dict):
                    telegram_entity = TelegramEntity.from_dict(
                        owner_id, telegram_entity
                    )

                should_insert = (
                    await TelegramUserMessageHandlers.__should_insert_message(
                        telegram_entity
                    )
                )
                if should_insert:
                    await telegram_entity.insert(session, commit=False)

        except Exception as e:
            logger.exception("Error getting telegram entity")
            raise e

        return should_insert

    @staticmethod
    async def incoming_message(client: Client, message: Message) -> None:
        assert message.chat is not None, "Message chat is None"
        assert client.me is not None, "Client is not authenticated"
        assert message.chat.id is not None, "Message chat ID is None"
        database = await DatabaseFactory.get_instance()

        owner_id = client.me.id
        chat_id = message.chat.id

        if message.chat.type not in TelegramUserMessageHandlers.SUPPORTED_CHAT_TYPES:
            return

        async with database.session() as session:
            should_insert = await TelegramUserMessageHandlers.__conditional_insert(
                session, client, message, owner_id, chat_id
            )

            if should_insert:
                await TelegramMessage.extract_chat_message_info(
                    message, owner_id, chat_id
                ).insert(session, commit=False)

    @property
    def summary_handlers(self) -> list[Handler]:
        return [
            MessageHandler(self.incoming_message, filters.text | ~filters.bot),
        ]
