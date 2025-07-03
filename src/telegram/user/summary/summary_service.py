from datetime import datetime, timedelta

from pyrogram.client import Client
from pyrogram.enums import ChatType

from src.telegram.user.summary.summary_schemas import TelegramEntity

SUPPORTED_CHAT_TYPES = [
    ChatType.GROUP,
    ChatType.SUPERGROUP,
    ChatType.CHANNEL,
    ChatType.PRIVATE,
]


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
