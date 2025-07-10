import logging

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.raw_update_handler import RawUpdateHandler
from pyrogram.raw.base.update import Update
from pyrogram.raw.types.peer_channel import PeerChannel
from pyrogram.raw.types.peer_chat import PeerChat
from pyrogram.raw.types.update_read_channel_inbox import UpdateReadChannelInbox
from pyrogram.raw.types.update_read_history_inbox import UpdateReadHistoryInbox
from pyrogram.types import Chat, User
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.database import DatabaseFactory
from src.telegram.user.summary.summary_schemas import TelegramEntity, TelegramMessage

logger = logging.getLogger("athena.telegram.user.summary.handlers")


class TelegramUserMessageHandlers:
    INBOX_UPDATE_FILTER_NAME = "inbox_update_filter"

    @staticmethod
    async def raw_update_processsor(
        client: Client,
        raw_update: Update,
        users: list[User],
        chats: list[Chat],
    ):
        is_read_history = isinstance(raw_update, UpdateReadHistoryInbox)
        is_read_channel = isinstance(raw_update, UpdateReadChannelInbox)

        if is_read_history or is_read_channel:
            assert client.me is not None
            owner_id = client.me.id
            database = await DatabaseFactory.get_instance()

            async with database.session() as session:
                # These updates show the messages the user has read
                if is_read_history:
                    await TelegramUserMessageHandlers.process_inbox_update(
                        owner_id, raw_update, session
                    )
                elif is_read_channel:
                    await TelegramUserMessageHandlers.process_channel_inbox_update(
                        owner_id, raw_update, session
                    )

    @staticmethod
    async def process_inbox_update(
        owner_id: int, update: UpdateReadHistoryInbox, session: AsyncSession
    ) -> None:
        """
        This type of update arrives from private chats and groups
        """
        peer = update.peer
        if isinstance(peer, PeerChannel):
            chat_id = peer.channel_id
        elif isinstance(peer, PeerChat):
            chat_id = peer.chat_id
        else:
            chat_id = peer.user_id

        max_id = update.max_id
        still_unread_count = update.still_unread_count

        await TelegramMessage.mark_as_read(session, owner_id, chat_id, max_id)
        await TelegramEntity.update_unread_count(
            session, owner_id, chat_id, still_unread_count
        )
        logger.debug("Processed private chat/group read update")

    @staticmethod
    async def process_channel_inbox_update(
        owner_id: int, update: UpdateReadChannelInbox, session: AsyncSession
    ) -> None:
        """
        This type of update arrives from supergroups and channels

        so channel_id can be either -XXXXXX or -100XXXXX
        """
        chat_id_unverified = update.channel_id
        max_id = update.max_id
        still_unread_count = update.still_unread_count

        # TODO: build a where statement w/ or_ to reduce the code duplication
        potential_id_1 = int(f"-100{chat_id_unverified}")
        potential_id_2 = int(f"-{chat_id_unverified}")

        # run for channel_id
        await TelegramMessage.mark_as_read(session, owner_id, potential_id_1, max_id)
        await TelegramEntity.update_unread_count(
            session, owner_id, potential_id_1, still_unread_count
        )

        # run for supergroup_id
        await TelegramMessage.mark_as_read(session, owner_id, potential_id_2, max_id)
        await TelegramEntity.update_unread_count(
            session, owner_id, potential_id_2, still_unread_count
        )
        logger.debug("Processed channel/supergroup read update")

    @property
    def inbox_filters(self) -> list[Handler]:
        return [
            RawUpdateHandler(
                self.raw_update_processsor,
                filters.all,
            ),
        ]
