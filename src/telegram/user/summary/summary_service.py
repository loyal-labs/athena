from datetime import datetime, timedelta
from typing import cast

from pyrogram.client import Client
from pyrogram.enums import ChatType
from pyrogram.raw.functions.contacts.get_top_peers import GetTopPeers
from pyrogram.raw.types.contacts.top_peers import TopPeers
from pyrogram.raw.types.peer_channel import PeerChannel
from pyrogram.raw.types.peer_chat import PeerChat
from pyrogram.raw.types.peer_user import PeerUser

from src.telegram.user.summary.summary_schemas import TelegramEntity

SUPPORTED_CHAT_TYPES = [
    ChatType.GROUP,
    ChatType.SUPERGROUP,
    ChatType.CHANNEL,
    ChatType.PRIVATE,
]
TOP_PEERS_LIMIT = 40


class SummaryService:
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

        response_array: list[TelegramEntity] = []

        async for dialog in client.get_dialogs():
            if dialog.chat.type not in SUPPORTED_CHAT_TYPES:
                continue

            if dialog.top_message and dialog.top_message.date:
                if dialog.top_message.date < stop_date:
                    break

            entity = TelegramEntity.from_dialog(dialog)
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
                print(type(peer))
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
