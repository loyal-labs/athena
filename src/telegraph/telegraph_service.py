import json
import logging
from enum import Enum
from typing import Any, cast

import markdown

from src.shared.base import BaseService
from src.shared.event_bus import Event, EventBus
from src.shared.event_registry import TelegraphPageTopics
from src.shared.secrets import OnePasswordManager
from src.telegraph.telegraph_model import TelegraphModel
from src.telegraph.telegraph_schemas import (
    Account,
    CreatePagePayload,
    GetPagePayload,
    NodeElement,
    Page,
    PageList,
    PageViews,
)
from src.telegraph.telegraph_utils import convert_html_to_telegraph_format

logger = logging.getLogger("athena.telegraph.service")


class TelegraphEnvFields(str, Enum):
    ACCESS_TOKEN = "TELEGRPAH_ACCESS_TOKEN"
    AUTHOR_NAME = "TELEGRPAH_AUTHOR_NAME"
    SHORT_NAME = "TELEGRPAH_SHORT_NAME"
    AUTHOR_URL = "TELEGRPAH_AUTHOR_URL"


class TelegraphService(BaseService):
    """
    Provides a high-level interface to interact with the Telegraph API.
    Uses TelegraphModel for raw API calls and schemas for data validation/parsing.
    """

    # 1Password Constants
    default_item_name = "ATHENA_TELEGRAPH"

    def __init__(self):
        self._model = TelegraphModel()
        self.access_token: str | None = None
        self.author_name: str | None = None
        self.short_name: str | None = None
        self.author_url: str | None = None

    @classmethod
    async def create(cls, secrets_manager: OnePasswordManager):
        """
        Creates a new instance of the TelegraphService.

        Args:
            secrets_manager: The secrets manager to use.

        Returns:
            TelegraphService: A new instance of the TelegraphService.
        """
        assert secrets_manager is not None, "Secrets manager is not set"
        assert isinstance(secrets_manager, OnePasswordManager), (
            "Secrets manager is not an instance of OnePasswordManager"
        )

        self = cls()
        await self.__init_service(secrets_manager)
        await self.__post_init_checks()

        return self

    # --- Private Methods ---
    async def __post_init_checks(self):
        assert self.access_token is not None, "Access token is not set"
        assert self.author_name is not None, "Author name is not set"
        assert self.short_name is not None, "Short name is not set"
        assert self.author_url is not None, "Author URL is not set"

    async def __init_service(self, secrets_manager: OnePasswordManager):
        assert secrets_manager is not None, "Secrets manager is not set"
        assert isinstance(secrets_manager, OnePasswordManager), (
            "Secrets manager is not an instance of OnePasswordManager"
        )
        assert secrets_manager.client is not None, "Secrets manager client is not set"

        fetched_secrets = await secrets_manager.get_secret_item(self.default_item_name)

        logger.debug("Fetching Telegraph environment variables")

        self.author_name = fetched_secrets.get(TelegraphEnvFields.AUTHOR_NAME.value)
        self.short_name = fetched_secrets.get(TelegraphEnvFields.SHORT_NAME.value)
        self.author_url = fetched_secrets.get(TelegraphEnvFields.AUTHOR_URL.value)
        self.access_token = fetched_secrets.get(TelegraphEnvFields.ACCESS_TOKEN.value)

    async def __prepare_markdown_content(self, content: str) -> list[dict[str, Any]]:
        try:
            html_content = markdown.markdown(content)
            telegraph_content = convert_html_to_telegraph_format(html_content)
            return cast(list[dict[str, Any]], telegraph_content)
        except Exception as e:
            logger.error("Error preparing markdown content: %s", e)
            raise ValueError(f"Error preparing markdown content: {e}") from e

    # --- Event Handlers ---
    @EventBus.subscribe(TelegraphPageTopics.CREATE_PAGE)
    async def on_create_page(self, event: Event) -> Page:
        """
        Creates a new Telegraph page.

        Args:
            title: The title of the page.
            content: The content of the page.

        Returns:
            A Page object representing the created page.
        """

        payload = cast(
            CreatePagePayload, event.extract_payload(event, CreatePagePayload)
        )
        title = payload.title
        content = payload.content

        page = await self.create_page(title, content, return_content=True)
        return page

    @EventBus.subscribe(TelegraphPageTopics.GET_PAGE)
    async def on_get_page(self, event: Event) -> Page:
        """
        Gets a Telegraph page.

        Args:
            path: The path of the page to get.

        Returns:
            A Page object representing the page.
        """

        payload = cast(GetPagePayload, event.extract_payload(event, GetPagePayload))
        path = payload.path
        page = await self.get_page(path, return_content=True)
        return page

    # --- Account Services ---
    async def create_account(
        self,
        short_name: str,
        author_name: str | None = None,
        author_url: str | None = None,
    ) -> Account:
        """
        Creates a new Telegraph account. Sets the service's access_token on success.

        Returns:
            An Account object including the new access_token.
        """
        raw_result = await self._model.create_account(
            short_name, author_name, author_url
        )
        account = Account.model_validate(raw_result)
        if account.access_token:
            self.access_token = (
                account.access_token
            )  # Store token for future use by this instance
        return account

    async def edit_account_info(
        self,
        short_name: str | None = None,
        author_name: str | None = None,
        author_url: str | None = None,
    ) -> Account:
        """
        Updates information about the Telegraph account.
        Requires access_token to be set on the service instance.
        """
        try:
            assert self.access_token is not None
        except AssertionError as e:
            raise ValueError("Access token is not set.") from e

        raw_result = await self._model.edit_account_info(
            self.access_token, short_name, author_name, author_url
        )
        return Account.model_validate(raw_result)

    async def get_account_info(self, fields: list[str] | None = None) -> Account:
        """
        Gets information about the Telegraph account
        """
        try:
            assert self.access_token is not None
        except AssertionError as e:
            raise ValueError("Access token is not set.") from e

        raw_result = await self._model.get_account_info(self.access_token, fields)
        return Account.model_validate(raw_result)

    async def revoke_access_token(self) -> Account:
        """
        Revokes the current access_token and generates a new one.
        Updates the service's access_token on success.
        Requires access_token to be set on the service instance.
        """
        try:
            assert self.access_token is not None
        except AssertionError as e:
            raise ValueError("Access token is not set.") from e

        raw_result = await self._model.revoke_access_token(self.access_token)
        account = Account.model_validate(raw_result)
        if account.access_token:
            self.access_token = account.access_token  # Update stored token
        return account

    # --- Page Services ---
    async def create_page(
        self,
        title: str,
        content: str,
        author_name: str | None = None,
        author_url: str | None = None,
        return_content: bool = False,
    ) -> Page:
        """
        Creates a new Telegraph page using the current access_token.
        Requires access_token to be set on the service instance.

        Args:
            title: Page title.
            content: List representing the page content (Array of Node).
            author_name: Optional author name.
            author_url: Optional author URL.
            return_content: If true, the content field will be returned.

        Returns:
            A Page object representing the created page.
        """
        try:
            assert self.access_token is not None
        except AssertionError as e:
            raise ValueError("Access token is not set.") from e

        prepared_content = await self.__prepare_markdown_content(content)

        raw_result = await self._model.create_page(
            access_token=self.access_token,
            title=title,
            content=prepared_content,
            author_name=author_name or self.author_name,
            author_url=author_url or self.author_url,
            return_content=return_content,
        )
        return Page.model_validate(raw_result)

    async def edit_page(
        self,
        path: str,
        title: str,
        content: list[str | dict[str, Any]],
        author_name: str | None = None,
        author_url: str | None = None,
        return_content: bool = False,
    ) -> Page:
        """
        Edits an existing Telegraph page using the current access_token.
        Requires access_token to be set on the service instance.
        See create_page for content format.
        """
        try:
            assert self.access_token is not None
        except AssertionError as e:
            raise ValueError("Access token is not set.") from e

        try:
            validated_nodes = [
                NodeElement.model_validate(n) if isinstance(n, dict) else n
                for n in content
            ]
            content_json = json.dumps(validated_nodes)
        except Exception as e:
            raise ValueError(f"Invalid content structure: {e}") from e

        raw_result = await self._model.edit_page(
            access_token=self.access_token,
            path=path,
            title=title,
            content_json=content_json,
            author_name=author_name or self.author_name,
            author_url=author_url or self.author_url,
            return_content=return_content,
        )
        return Page.model_validate(raw_result)

    async def get_page(self, path: str, return_content: bool = True) -> Page:
        """
        Gets a Telegraph page. Does not require an access token.
        """
        raw_result = await self._model.get_page(path, return_content)
        return Page.model_validate(raw_result)

    async def get_page_list(self, offset: int = 0, limit: int = 50) -> PageList:
        """
        Gets a list of pages belonging to the Telegraph account associated
        with the current access_token.
        Requires access_token to be set on the service instance.
        """
        try:
            assert self.access_token is not None
        except AssertionError as e:
            raise ValueError("Access token is not set.") from e

        raw_result = await self._model.get_page_list(self.access_token, offset, limit)
        return PageList.model_validate(raw_result)

    async def get_views(
        self,
        path: str,
        year: int | None = None,
        month: int | None = None,
        day: int | None = None,
        hour: int | None = None,
    ) -> PageViews:
        """
        Gets the number of views for a Telegraph article.
        """
        raw_result = await self._model.get_views(path, year, month, day, hour)
        return PageViews.model_validate(raw_result)
