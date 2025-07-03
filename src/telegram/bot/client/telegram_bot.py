import logging
from enum import Enum
from pathlib import Path

from pyrogram.client import Client
from pyrogram.enums import ParseMode
from pyrogram.handlers.handler import Handler
from pyrogram.methods.utilities.idle import idle

from src.shared.secrets import OnePasswordManager

logger = logging.getLogger("athena.telegram.client")


class TelegramBotStatus(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"


class TelegramEnvFields(Enum):
    BOT_TOKEN = "TELEGRAM_BOT_TOKEN"
    API_ID = "TELEGRAM_API_ID"
    API_HASH = "TELEGRAM_API_HASH"


class TelegramBot:
    """Telegram bot client."""

    status: TelegramBotStatus = TelegramBotStatus.STOPPED
    bot_session_dir: Path = Path("tmp/")
    bot_session_name: str = "athena_session"

    # 1Password Constants
    default_item_name = "ATHENA_TELEGRAM"

    def __init__(self):
        self.api_token: str | None = None
        self.api_id: str | None = None
        self.api_hash: str | None = None
        self.client: Client | None = None

    @classmethod
    async def create(cls, secrets_manager: OnePasswordManager):
        """Asynchronously creates and initializes a Telegram bot client."""
        assert secrets_manager is not None, "Secrets manager is not set"
        assert isinstance(secrets_manager, OnePasswordManager), (
            "Secrets manager is not an instance of OnePasswordManager"
        )

        self = cls()
        await self.__init_client(secrets_manager)
        await self.__post_init_checks()
        return self

    # --- Private Methods ---
    async def __post_init_checks(self):
        assert self.api_token is not None, "API token is not set"
        assert self.api_id is not None, "API ID is not set"
        assert self.api_hash is not None, "API hash is not set"

    async def __init_client(self, secrets_manager: OnePasswordManager) -> Client:
        """
        Initializes the Telegram bot client.

        Args:
            secrets_manager: The secrets manager to use.

        Returns:
            The initialized Telegram bot client.
        """
        assert secrets_manager is not None, "Secrets manager is not set"
        assert isinstance(secrets_manager, OnePasswordManager), (
            "Secrets manager is not an instance of OnePasswordManager"
        )
        assert secrets_manager.client is not None, "Secrets manager client is not set"

        logger.debug("Fetching Telegram environment variables")
        fetched_secrets = await secrets_manager.get_secret_item(self.default_item_name)

        self.api_token = fetched_secrets.get(TelegramEnvFields.BOT_TOKEN.value)
        self.api_id = fetched_secrets.get(TelegramEnvFields.API_ID.value)
        self.api_hash = fetched_secrets.get(TelegramEnvFields.API_HASH.value)

        self.client = Client(
            name=self.bot_session_name,
            api_id=self.api_id,
            api_hash=self.api_hash,
            bot_token=self.api_token,
            workdir=str(self.bot_session_dir),
        )

        return self.client

    async def _setup_client(self) -> None:
        """
        Sets up parameters for the Telegram bot client.
        """
        assert self.client is not None, "Client is not initialized"
        self.client.set_parse_mode(ParseMode.HTML)

    def get_status(self) -> TelegramBotStatus:
        return self.status

    def get_client(self) -> Client:
        assert self.client is not None, "Client is not initialized"
        return self.client

    def change_status(self, status: TelegramBotStatus) -> None:
        self.status = status
        logger.debug("Client status: %s", self.status.value)

    async def register_handlers(self, handlers: list[Handler]) -> None:
        assert self.client is not None, "Client is not initialized"
        for handler in handlers:
            logger.debug("Adding handler: %s", handler)
            self.client.add_handler(handler)

    async def start(
        self, blocking: bool = False, handlers: list[Handler] | None = None
    ) -> None:
        """
        Starts the Telegram bot client.

        Args:
            blocking: Blocks the main thread and listens for the updates.
            handlers: The handlers to register.
        """
        assert self.client is not None, "Client is not initialized"

        await self.client.start()
        logger.debug("Client started")
        await self._setup_client()
        logger.debug("Client setup complete")
        self.change_status(TelegramBotStatus.RUNNING)

        if handlers:
            await self.register_handlers(handlers)

        if blocking:
            await idle()  # type: ignore
            await self.client.stop()

    async def stop(self) -> None:
        assert self.client is not None, "Client is not initialized"

        await self.client.stop()
        self.change_status(TelegramBotStatus.STOPPED)
