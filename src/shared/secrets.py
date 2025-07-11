import asyncio
import logging
import os
from typing import cast

from dotenv import load_dotenv
from onepasswordconnectsdk.client import Client, Item, new_client
from onepasswordconnectsdk.models.field import Field
from pydantic import BaseModel

logger = logging.getLogger("athena.shared.secrets")


class SecretsSchema(BaseModel):
    secrets: dict[str, str]

    def get(self, key: str) -> str:
        result = self.secrets.get(key)
        assert result is not None, f"Key {key} not found"
        return result


load_dotenv()


class OnePasswordManager:
    """
    Secrets manager. Currently supports only 1Password.
    """

    default_vault: str = "loyalvars"
    secret_value = "ONEPASS_CONNECT_TOKEN"
    host_value = "ONEPASS_CONNECT_HOST"

    def __init__(self):
        self.client: Client | None = None
        self.host: str | None = None
        self.default_vault_uuid: str | None = None
        self.frontend_url: str | None = None

        self.deployment: str = "local"

    @classmethod
    async def create(cls):
        """
        Creates a new instance of the OnePasswordManager.

        Returns:
            OnePasswordManager: A new instance of the OnePasswordManager.
        """

        logger.info("Creating OnePasswordManager")
        service_token = os.getenv(cls.secret_value, "")
        host = os.getenv(cls.host_value, "")
        frontend_url = os.getenv("FRONTEND_URL")

        assert service_token is not None, f"{cls.secret_value} is not set"
        assert host is not None, f"{cls.host_value} is not set"
        logger.info("Fetched OnePassword service token")

        self = cls()
        self.deployment = os.getenv("GLOBAL_APP_ENV", "local")
        self.host = host
        self.frontend_url = frontend_url
        assert self.frontend_url is not None, "FRONTEND_URL is required"

        await self.__init_client(service_token)
        logger.info("OnePasswordManager initialized")
        return self

    # --- Private Methods ---
    async def __init_client(
        self,
        service_token: str,
    ) -> Client:
        assert service_token is not None, "OP_SERVICE_ACCOUNT_TOKEN is not set"
        assert self.host is not None, "ONEPASS_CONNECT_HOST is not set"

        try:
            client: Client = new_client(self.host, service_token)
            vault_info = client.get_vault_by_title(self.default_vault)  # type: ignore
            assert vault_info is not None, "Vault not found"
            vault_uuid = vault_info.id  # type: ignore
            self.default_vault_uuid = vault_uuid
        except Exception as e:
            logger.exception("Error initializing client")
            raise e

        logger.debug("Client initialized")
        self.client = client
        return client

    async def get_secret_file(self, item_name: str, file_id: str) -> str:
        assert self.client is not None, "Client is not initialized"
        assert self.default_vault_uuid is not None, "Vault UUID is not set"
        assert item_name is not None, "Item name is not set"
        assert file_id is not None, "File ID is not set"

        item = cast(
            Item, self.client.get_item_by_title(item_name, self.default_vault_uuid)
        )
        assert item is not None, "Item is not set"
        assert isinstance(item, Item), "Item is not an Item"
        item_id = cast(str, item.id)  # type: ignore

        files = self.client.get_file_content(file_id, item_id, self.default_vault_uuid)
        files = files.decode("utf-8")
        return files

    async def get_secret_item(self, item_name: str) -> SecretsSchema:
        assert self.client is not None, "Client is not initialized"
        assert self.default_vault_uuid is not None, "Vault UUID is not set"
        assert item_name is not None, "Item name is not set"

        response_dict: SecretsSchema = SecretsSchema(secrets={})

        try:
            logger.debug("Getting secret for %s", item_name)
            item = cast(
                Item, self.client.get_item_by_title(item_name, self.default_vault_uuid)
            )
            assert item is not None, "Item is not set"
            assert isinstance(item, Item), "Item is not an Item"
            fields = cast(list[Field], item.fields)  # type: ignore
            assert fields is not None, "Item has no fields"

            for field in fields:
                try:
                    assert field.label is not None, "Field label is not set"  # type: ignore
                    assert field.value is not None, "Field value is not set"  # type: ignore
                except AssertionError:
                    continue
                except Exception as e:
                    logger.exception("Error getting secret %s", item_name)
                    raise e
                response_dict.secrets[field.label] = field.value  # type: ignore

        except Exception as e:
            logger.exception("Error getting secret")
            raise e

        return response_dict


class SecretsFactory:
    """Global singleton factory for Secrets."""

    _instance: OnePasswordManager | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> OnePasswordManager:
        """Get or create singleton instance of OnePasswordManager."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    logger.info("Creating Database singleton")
                    cls._instance = await OnePasswordManager.create()
                    logger.info("Database singleton created")
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None
