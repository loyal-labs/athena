import logging

from pyrogram.client import Client
from pyrogram.enums import ParseMode
from pyrogram.handlers.handler import Handler
from pyrogram.methods.utilities.idle import idle

from src.shared.config import shared_config
from src.telegram.client.client_config import (
    TelegramBotData,
    TelegramBotStatus,
    TelegramConfig,
)

logger = logging.getLogger("athena.telegram.client")


class TelegramBot:
    """Telegram bot client."""

    status: TelegramBotStatus = TelegramBotStatus.STOPPED

    def __init__(
        self,
        config: TelegramConfig,
    ) -> None:
        logger.debug("Initializing Telegram bot with .env config")
        self.data = TelegramBotData()
        self.api_token = config.bot_token

        in_memory = shared_config.app_env == "cloud"

        self.client = Client(
            name=config.bot_session_name,
            api_id=config.api_id,
            api_hash=config.api_hash,
            bot_token=self.api_token,
            workdir=str(config.bot_session_dir),
            in_memory=in_memory,
        )
        logger.debug("Client object initialized")

    async def _fill_session_data(self) -> None:
        await self.data.fill_from_client(self.client)
        logger.debug("Filled session data")

    async def _setup_client(self) -> None:
        self.client.set_parse_mode(ParseMode.HTML)

    def get_status(self) -> TelegramBotStatus:
        return self.status

    def get_data(self) -> TelegramBotData:
        return self.data

    def get_client(self) -> Client:
        return self.client

    def change_status(self, status: TelegramBotStatus) -> None:
        self.status = status
        logger.debug("Client status: %s", self.status.value)

    async def register_handlers(self, handlers: list[Handler]) -> None:
        for handler in handlers:
            logger.debug("Adding handler: %s", handler)
            self.client.add_handler(handler)

    async def start(
        self, blocking: bool = False, handlers: list[Handler] | None = None
    ) -> None:
        await self.client.start()
        logger.debug("Client started")
        await self._fill_session_data()
        await self._setup_client()
        logger.debug("Client setup complete")
        self.change_status(TelegramBotStatus.RUNNING)

        if handlers:
            await self.register_handlers(handlers)

        if blocking:
            await idle()  # type: ignore
            await self.client.stop()

    async def stop(self) -> None:
        await self.client.stop()
        self.change_status(TelegramBotStatus.STOPPED)
