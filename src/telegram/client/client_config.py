import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import cast

from google.auth import default as google_default_credentials  # type: ignore
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings
from pyrogram.client import Client

from src.shared.config import get_secret

logger = logging.getLogger("athena.telegram.client")


class TelegramBotStatus(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"


class TelegramConfig(BaseSettings):
    """Settings for the Telegram bot."""

    # DEFAULT VALUES
    bot_session_dir: Path = Path("tmp/")
    bot_session_name: str = "athena_session"

    # GOOGLE CLOUD VARIABLES
    google_project_id: str | None = Field(None, validation_alias="GOOGLE_CLOUD_PROJECT")
    api_id_secret_id: str | None = Field(None, validation_alias="API_ID_SECRET_ID")
    api_hash_secret_id: str | None = Field(None, validation_alias="API_HASH_SECRET_ID")
    bot_token_secret_id: str | None = Field(None, validation_alias="API_BOT_TOKEN")

    class Config:
        extra = "ignore"
        env_file = ".env"
        env_prefix = "TELEGRAM_"

    @computed_field(return_type=int)  # type: ignore
    @property
    def api_id(self) -> int:
        """Fetch TELEGRAM_API_ID from Secret Manager or local environment."""
        if not self.api_id_secret_id:
            local_api_id = os.environ.get("TELEGRAM_API_ID")
            if local_api_id:
                logger.warning(
                    "Using TELEGRAM_API_ID env var for local dev. "
                    "Set API_ID_SECRET_ID for deployed environments."
                )
                return int(local_api_id)
        if not self.google_project_id:
            # Auto-detect project ID
            try:
                _creds, detected_project_id = google_default_credentials()  # type: ignore
                if detected_project_id:
                    self.google_project_id = cast(str, detected_project_id)
                else:
                    raise ValueError("Could not auto-detect Google Cloud Project ID.")
            except Exception as e:
                raise ValueError(
                    f"Failed to get Google Cloud Project ID for secret fetching: {e}"
                ) from e
        logger.debug(
            f"Attempting to fetch secret '{self.api_id_secret_id}' "
            f"from project '{self.google_project_id}'"
        )
        fetched_api_id = get_secret(self.google_project_id, self.api_id_secret_id)  # type: ignore
        if fetched_api_id is None:
            raise ValueError(
                f"Failed to fetch API ID from Secret Manager "
                f"(Secret ID: {self.api_id_secret_id}). Check logs and permissions."
            )
        return int(fetched_api_id)

    @computed_field(return_type=str)  # type: ignore
    @property
    def api_hash(self) -> str:
        """Fetch TELEGRAM_API_HASH from Secret Manager or local environment."""
        if not self.api_hash_secret_id:
            local_api_hash = os.environ.get("TELEGRAM_API_HASH")
            if local_api_hash:
                logger.warning(
                    "Using TELEGRAM_API_HASH env var for local dev. "
                    "Set API_HASH_SECRET_ID for deployed environments."
                )
                return local_api_hash
        if not self.google_project_id:
            # Auto-detect project ID
            try:
                _creds, detected_project_id = google_default_credentials()  # type: ignore
                if detected_project_id:
                    self.google_project_id = cast(str, detected_project_id)
                else:
                    raise ValueError("Could not auto-detect Google Cloud Project ID.")
            except Exception as e:
                raise ValueError(
                    f"Failed to get Google Cloud Project ID for secret fetching: {e}"
                ) from e
        logger.debug(
            f"Attempting to fetch secret '{self.api_hash_secret_id}' "
            f"from project '{self.google_project_id}'"
        )
        fetched_api_hash = get_secret(self.google_project_id, self.api_hash_secret_id)  # type: ignore
        if fetched_api_hash is None:
            raise ValueError(
                f"Failed to fetch API hash from Secret Manager "
                f"(Secret ID: {self.api_hash_secret_id}). Check logs and permissions."
            )
        return fetched_api_hash

    @computed_field(return_type=str)  # type: ignore
    @property
    def bot_token(self) -> str:
        """Fetch TELEGRAM_BOT_TOKEN from Secret Manager or local environment."""
        if not self.bot_token_secret_id:
            local_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
            if local_bot_token:
                logger.warning(
                    "Using TELEGRAM_BOT_TOKEN env var for local dev. "
                    "Set BOT_TOKEN_SECRET_ID for deployed environments."
                )
                return local_bot_token
        if not self.google_project_id:
            # Auto-detect project ID
            try:
                _creds, detected_project_id = google_default_credentials()  # type: ignore
                if detected_project_id:
                    self.google_project_id = cast(str, detected_project_id)
                else:
                    raise ValueError("Could not auto-detect Google Cloud Project ID.")
            except Exception as e:
                raise ValueError(
                    f"Failed to get Google Cloud Project ID for secret fetching: {e}"
                ) from e
        logger.debug(
            f"Attempting to fetch secret '{self.bot_token_secret_id}' "
            f"from project '{self.google_project_id}'"
        )
        fetched_bot_token = get_secret(self.google_project_id, self.bot_token_secret_id)  # type: ignore
        if fetched_bot_token is None:
            raise ValueError(
                f"Failed to fetch bot token from Secret Manager "
                f"(Secret ID: {self.bot_token_secret_id}). Check logs and permissions."
            )
        return fetched_bot_token


@dataclass
class TelegramBotData:
    peer_id: int | None = None
    name: str | None = None
    username: str | None = None

    async def fill_from_client(self, client: Client) -> None:
        bot_info = await client.get_me()
        self.peer_id = bot_info.id
        self.name = bot_info.first_name
        self.username = bot_info.username
        logger.debug("Bot info: %s", self)
