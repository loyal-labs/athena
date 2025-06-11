import logging
import os

from dotenv import load_dotenv
from onepassword import Client

logger = logging.getLogger("athena.shared.secrets")


class OnePasswordManager:
    """
    Secrets manager. Currently supports only 1Password.
    """

    prefix = "op://"
    default_vault = "loyalvars"
    one_password_schema = "op://{vault_name}/{item_name}/{field_name}"
    integration_name = "Loyal Athena"
    integration_version = "0.0.1"

    def __init__(self):
        self.client = None

    @classmethod
    async def create(cls):
        """
        Creates a new instance of the OnePasswordManager.

        Returns:
            OnePasswordManager: A new instance of the OnePasswordManager.
        """
        load_dotenv()

        service_token = os.getenv("ONEPASS_SERVICE_TOKEN", "")
        assert service_token is not None, "ONEPASS_SERVICE_TOKEN is not set"

        self = cls()

        await self.__init_client(service_token)
        return self

    # --- Private Methods ---
    async def __init_client(
        self,
        service_token: str,
    ) -> Client:
        assert service_token is not None, "ONEPASS_SERVICE_TOKEN is not set"

        client = await Client.authenticate(
            auth=service_token,
            integration_name=self.integration_name,
            integration_version=self.integration_version,
        )
        self.client = client
        return client

    def __build_one_password_schema(
        self, vault_name: str, item_name: str, field_name: str
    ) -> str:
        return self.one_password_schema.format(
            vault_name=vault_name,
            item_name=item_name,
            field_name=field_name,
        )

    async def get_secret(self, vault_name: str, item_name: str, field_name: str) -> str:
        assert self.client is not None, "Client is not initialized"
        assert vault_name is not None, "Vault name is not set"
        assert field_name is not None, "Field name is not set"
        assert item_name is not None, "Item name is not set"

        try:
            path = self.__build_one_password_schema(vault_name, item_name, field_name)
            return await self.client.secrets.resolve(path)
        except Exception as e:
            logger.exception("Error getting secret")
            raise e
