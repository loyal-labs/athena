import logging

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types import Message

logger = logging.getLogger("athena.telegram.user.summary.handlers")


class SummaryHandlers:
    @staticmethod
    async def incoming_message(client: Client, message: Message) -> None:
        print(message)

    @property
    def summary_handlers(self) -> list[Handler]:
        return [
            MessageHandler(self.incoming_message, filters.incoming),
        ]
