import logging

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types import Message

logger = logging.getLogger("athena.telegram.login.handlers")


class LoginHandlers:
    """
    Login handlers class
    """

    @staticmethod
    async def login_message(client: Client, message: Message) -> None:
        pass

    @property
    def login_handlers(self) -> list[Handler]:
        return [
            MessageHandler(self.login_message, filters.incoming),
        ]
