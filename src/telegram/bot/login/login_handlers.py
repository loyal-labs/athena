import logging

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.enums import MessageServiceType
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types import Message

logger = logging.getLogger("athena.telegram.login.handlers")


class LoginHandlers:
    """
    Login handlers class
    """

    async def shared_data_filter(self, _, client: Client, message: Message) -> bool:
        if (
            message.service is not None
            and message.service == MessageServiceType.WEB_APP_DATA
        ):
            return True
        return False

    async def login_message(self, client: Client, message: Message) -> None:
        pass

    @property
    def login_handlers(self) -> list[Handler]:
        shared_data_filter = filters.create(self.shared_data_filter)  # type: ignore

        return [
            MessageHandler(self.login_message, filters.incoming & shared_data_filter),
        ]
