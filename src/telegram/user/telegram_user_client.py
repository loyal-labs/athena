import logging

from pyrogram.client import Client
from pyrogram.enums import ParseMode
from pyrogram.handlers.handler import Handler
from pyrogram.methods.utilities.idle import idle

from src.shared.secrets import OnePasswordManager, SecretsFactory
from src.telegram.user.storage.telegram_storage import PostgresStorage

logger = logging.getLogger("athena.telegram.user")


class TelegramUser:
    """
    Telegram user client
    """

    default_item_value = "ATHENA_TELEGRAM"
    api_id_value = "TELEGRAM_API_ID"
    api_hash_value = "TELEGRAM_API_HASH"

    def __init__(self):
        self.api_id: str | None = None
        self.api_hash: str | None = None
        self.dc_id: int | None = None
        self.user_id: int | None = None
        self.client: Client | None = None
        self.storage: PostgresStorage | None = None
        self.session_name: str | None = None

    @classmethod
    async def create(cls, dc_id: int, auth_key: bytes, user_id: int):
        """Asynchronously creates and initializes a Telegram user client."""
        secrets_manager = await SecretsFactory.get_instance()

        self = cls()

        # Initialize the client
        await self.__init_session(secrets_manager, dc_id, auth_key, user_id)
        await self.__init_client()

        return self

    async def __init_session(
        self,
        secrets_manager: OnePasswordManager,
        dc_id: int,
        auth_key: bytes,
        user_id: int,
    ) -> None:
        assert len(auth_key) == 256, "auth_key must be 256 bytes"
        # Pack the values into a binary blob
        telegram_client_secret = await secrets_manager.get_secret_item(
            self.default_item_value
        )

        self.api_id = telegram_client_secret.get(self.api_id_value)
        self.api_hash = telegram_client_secret.get(self.api_hash_value)
        self.dc_id = dc_id
        self.user_id = user_id

        self.storage = await PostgresStorage.create(
            dc_id, int(self.api_id), auth_key, user_id, False, False
        )

        self.session_name = f"telegram_session_{user_id}"

    async def __init_client(self):
        """Initializes the Telegram client."""
        assert self.session_name is not None, "Session name is not initialized"
        assert self.api_id is not None, "API ID is not initialized"
        assert self.api_hash is not None, "API hash is not initialized"
        assert self.storage is not None, "Storage is not initialized"

        self.client = Client(
            name=self.session_name,
            api_id=self.api_id,
            api_hash=self.api_hash,
            storage_engine=self.storage,
        )

    async def __setup_client(self):
        """Sets up the Telegram client."""
        assert self.client is not None, "Client is not initialized"
        self.client.set_parse_mode(ParseMode.HTML)

    def get_client(self) -> Client:
        """Returns the Telegram client."""
        assert self.client is not None, "Client is not initialized"
        return self.client

    async def register_handlers(self, handlers: list[Handler]) -> None:
        """Registers the handlers to the Telegram client."""
        assert self.client is not None, "Client is not initialized"
        for idx, handler in enumerate(handlers):
            self.client.add_handler(handler, idx)

    async def start(
        self, blocking: bool = False, handlers: list[Handler] | None = None
    ):
        """Starts the Telegram client."""
        assert self.client is not None, "Client is not initialized"
        await self.client.start()
        logger.debug("Client started")
        await self.__setup_client()
        logger.debug("Client setup complete")

        if handlers:
            await self.register_handlers(handlers)

        if blocking:
            await idle()
            await self.client.stop()

    async def stop(self) -> None:
        """Stops the Telegram client."""
        assert self.client is not None, "Client is not initialized"
        await self.client.stop()
