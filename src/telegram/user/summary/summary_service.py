from datetime import datetime, timedelta
from logging import getLogger
from typing import cast

import pandas as pd
from pyrogram.client import Client
from pyrogram.enums import ChatType
from pyrogram.raw.functions.contacts.get_top_peers import GetTopPeers
from pyrogram.raw.types.contacts.top_peers import TopPeers
from pyrogram.raw.types.peer_channel import PeerChannel
from pyrogram.raw.types.peer_chat import PeerChat
from pyrogram.raw.types.peer_user import PeerUser
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.database import Database
from src.telegram.user.summary.summary_dspy import summarize_chat_messages
from src.telegram.user.summary.summary_schemas import (
    TelegramChatSummary,
    TelegramEntity,
    TelegramMessage,
)

SUPPORTED_CHAT_TYPES = [
    ChatType.GROUP,
    ChatType.SUPERGROUP,
    ChatType.CHANNEL,
    ChatType.PRIVATE,
]
TOP_PEERS_LIMIT = 40

logger = getLogger("telegram.user.summary.summary_service")


class SummaryService:
    async def mark_as_read(
        self, client: Client, chat_id: int, max_id: int | None = None
    ) -> None:
        assert client is not None, "Client is required"
        assert isinstance(client, Client), "Client must be an instance of Client"
        assert chat_id is not None, "Chat ID is required"

        if max_id is None:
            await client.read_chat_history(chat_id)
        else:
            await client.read_chat_history(chat_id, max_id=max_id)

    async def isolate_interests(self, client: Client) -> pd.DataFrame:
        """
        Isolate interests from the dialogs.
        """
        assert client is not None, "Client is required"
        assert isinstance(client, Client), "Client must be an instance of Client"

        logger.debug("Getting dialogs...")
        dialogs = await self.get_recent_dialogs(client)
        dialogs_array_dict = [dialog.model_dump() for dialog in dialogs]
        dialogs_df = pd.DataFrame(dialogs_array_dict)

        logger.debug("Getting top peers rating...")
        top_peers_rating = await self.get_top_peers_rating(client)
        top_peers_rating_df = pd.DataFrame(
            top_peers_rating.items(), columns=["chat_id", "rating"]
        )

        # Merge dialogs and top peers rating
        logger.debug("Merging dialogs and top peers rating...")
        dialogs_df["rating"] = dialogs_df["chat_id"].map(  # type: ignore
            top_peers_rating_df.set_index("chat_id")["rating"]  # type: ignore
        )

        # Isolate personal chats
        personal_df = dialogs_df[dialogs_df["chat_type"] == "PRIVATE"]

        # Isolate group chats
        group_df = dialogs_df[dialogs_df["chat_type"].isin(["GROUP", "SUPERGROUP"])]  # type: ignore
        group_df = group_df[group_df["rating"] > 0]

        # Isolate channels
        channels_df = dialogs_df[dialogs_df["chat_type"] == "CHANNEL"]
        channels_df_with_rating = channels_df[channels_df["rating"] > 0]
        channels_df_read = channels_df[channels_df["unread_count"] < 10]

        # Concatenate all dataframes
        final_df = pd.concat(
            [personal_df, group_df, channels_df_with_rating, channels_df_read]
        )
        # drop duplicates by chat_id
        final_df = final_df.drop_duplicates(subset=["chat_id"])
        final_df = final_df.sort_values(by="rating", ascending=False)  # type: ignore
        return final_df

    async def get_recent_messages(
        self,
        client: Client,
        chat_id: int,
        day_offset: int = 30,
        username: str | None = None,
    ) -> list[TelegramMessage]:
        assert client is not None, "Client is required"
        assert isinstance(client, Client), "Client must be an instance of Client"
        assert day_offset > 0, "Day offset must be greater than 0"

        start_date = datetime.now()
        stop_date = start_date - timedelta(days=day_offset)
        owner_id = client.me.id if client.me else -1

        messages: list[TelegramMessage] = []

        logger.debug(f"Getting recent messages for chat {chat_id}...")

        chosen_param = username if username else chat_id
        async for message in client.get_chat_history(chosen_param, limit=100):
            if message.date and message.date < stop_date:
                break

            if message.text:
                messages.append(
                    TelegramMessage.extract_chat_message_info(
                        message, owner_id, chat_id
                    )
                )
        logger.debug(f"Found {len(messages)} messages")
        return messages

    async def check_for_unread_summaries(
        self, owner_id: int, session: AsyncSession
    ) -> bool:
        """
        Checks if there are any unread summaries or we need to create new ones.
        """
        assert session is not None, "Session is required"
        assert isinstance(session, AsyncSession), (
            "Session must be an instance of AsyncSession"
        )

        count = await TelegramChatSummary.count_processed_unread_summary(
            owner_id, session
        )
        return count > 0

    async def create_chat_summary(
        self,
        owner_id: int,
        chat_id: int,
        session: AsyncSession,
        chat_name: str,
        chat_type: str,
        unread_count: int | None = None,
    ) -> TelegramChatSummary:
        assert chat_id is not None, "Chat ID is required"
        assert session is not None, "Session is required"
        assert isinstance(session, AsyncSession), (
            "Session must be an instance of AsyncSession"
        )
        if chat_type == "CHANNEL":
            limit = unread_count
        else:
            limit = None

        messages = await TelegramMessage.get_messages_for_chat(
            owner_id, chat_id, session, limit
        )
        summary = await summarize_chat_messages(messages, chat_name, chat_type)
        summary_obj = TelegramChatSummary.from_pipeline_output(
            owner_id, chat_id, summary
        )
        # await TelegramChatSummary.update_topics(summary_obj, session)
        return summary_obj

    async def get_unread_messages_from_chat(
        self,
        client: Client,
        chat_id: int,
    ) -> list[TelegramMessage]:
        assert client is not None, "Client is required"
        assert client.me is not None, "Client must be logged in"
        assert isinstance(client, Client), "Client must be an instance of Client"
        assert chat_id is not None, "Chat ID is required"

        unread_count_context_offset = 20
        unread_count_no_offset_limit = 100

        owner_id = client.me.id
        get_chat = await client.get_chat(chat_id)
        unread_count = get_chat.unread_count
        if unread_count is None or unread_count == 0:
            return []

        response_messages: list[TelegramMessage] = []

        if unread_count < unread_count_no_offset_limit:
            unread_count += unread_count_context_offset

        async for message in client.get_chat_history(chat_id, limit=unread_count):
            msg_obj = TelegramMessage.extract_chat_message_info(
                message, owner_id, chat_id
            )
            response_messages.append(msg_obj)

        return response_messages

    async def insert_unread_messages(
        self,
        client: Client,
        chat_id: int,
        db: Database,
    ) -> None:
        assert client is not None, "Client is required"
        assert isinstance(client, Client), "Client must be an instance of Client"
        assert chat_id is not None, "Chat ID is required"
        assert db is not None, "Database is required"
        assert isinstance(db, Database), "Database must be an instance of Database"

        unread_messages = await self.get_unread_messages_from_chat(client, chat_id)
        async with db.session() as session:
            await TelegramMessage.insert_many(unread_messages, session)

    async def get_recent_dialogs(
        self, client: Client, day_offset: int = 30
    ) -> list[TelegramEntity]:
        """
        Pyrogram processes messages sequentially.
        Request dialogs active in the last X days.

        Args:
            client: Pyrogram client
            day_offset: Number of days to look back

        Returns:
            List of TelegramEntity objects
        """
        assert client is not None, "Client is required"
        assert isinstance(client, Client), "Client must be an instance of Client"
        assert day_offset > 0, "Day offset must be greater than 0"

        start_date = datetime.now()
        stop_date = start_date - timedelta(days=day_offset)

        user_id = client.me.id if client.me else -1

        response_array: list[TelegramEntity] = []

        async for dialog in client.get_dialogs(limit=500):
            chat_type = dialog.chat.type
            if chat_type not in SUPPORTED_CHAT_TYPES:
                continue

            if dialog.top_message and dialog.top_message.date:
                if dialog.top_message.date < stop_date:
                    break

            entity = TelegramEntity.from_dialog(dialog, user_id)
            response_array.append(entity)

        return response_array

    async def check_number_of_messages(
        self, client: Client, username: str, from_user: str
    ) -> int:
        assert client is not None, "Client is required"
        assert isinstance(client, Client), "Client must be an instance of Client"
        assert username is not None, "Username is required"
        assert from_user is not None, "From user is required"

        response = await client.search_messages_count(username, from_user=from_user)

        return response

    async def get_top_peers_rating(
        self, client: Client, limit: int = TOP_PEERS_LIMIT
    ) -> dict[int, float]:
        """
        Get the top peers rating for the last 20 days.
        Helps build an unique user profile.

        Args:
            client: Pyrogram client
            limit: Number of top peers to get

        Returns:
            Dictionary of entity_id and rating
        """
        assert client is not None, "Client is required"
        assert isinstance(client, Client), "Client must be an instance of Client"
        assert limit > 0, "Limit must be greater than 0"

        results = await client.invoke(  # type: ignore
            GetTopPeers(
                offset=0,
                limit=limit,
                hash=20,
                correspondents=True,
                forward_users=True,
                forward_chats=True,
                groups=True,
                channels=True,
            )
        )
        results = cast(TopPeers, results)
        categories = results.categories
        resuls_dict: dict[int, float] = {}

        for category in categories:
            for outet_peer in category.peers:
                entity_id = None
                peer = outet_peer.peer
                if isinstance(peer, PeerUser):
                    entity_id = peer.user_id
                elif isinstance(peer, PeerChannel):
                    entity_id = int(f"-100{peer.channel_id}")
                elif isinstance(peer, PeerChat):  # type: ignore
                    entity_id = int(f"-{peer.chat_id}")

                if entity_id is not None:
                    if entity_id not in resuls_dict:
                        resuls_dict[entity_id] = outet_peer.rating
                    else:
                        resuls_dict[entity_id] += outet_peer.rating

        return resuls_dict
