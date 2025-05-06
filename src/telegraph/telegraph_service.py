import json
from typing import Any

from src.shared.base import BaseService
from src.telegraph.telegraph_model import TelegraphModel
from src.telegraph.telegraph_schemas import (
    Account,
    NodeElement,
    Page,
    PageList,
    PageViews,
)


class TelegraphService(BaseService):
    """
    Provides a high-level interface to interact with the Telegraph API.
    Uses TelegraphModel for raw API calls and schemas for data validation/parsing.
    """

    def __init__(self, access_token: str | None = None):
        self._model = TelegraphModel()
        self.access_token = access_token

    # --- Account Services ---
    def create_account(
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
        raw_result = self._model.create_account(short_name, author_name, author_url)
        account = Account.model_validate(raw_result)
        if account.access_token:
            self.access_token = (
                account.access_token
            )  # Store token for future use by this instance
        return account

    def edit_account_info(
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

        raw_result = self._model.edit_account_info(
            self.access_token, short_name, author_name, author_url
        )
        return Account.model_validate(raw_result)

    def get_account_info(self, fields: list[str] | None = None) -> Account:
        """
        Gets information about the Telegraph account
        """
        try:
            assert self.access_token is not None
        except AssertionError as e:
            raise ValueError("Access token is not set.") from e

        raw_result = self._model.get_account_info(self.access_token, fields)
        return Account.model_validate(raw_result)

    def revoke_access_token(self) -> Account:
        """
        Revokes the current access_token and generates a new one.
        Updates the service's access_token on success.
        Requires access_token to be set on the service instance.
        """
        try:
            assert self.access_token is not None
        except AssertionError as e:
            raise ValueError("Access token is not set.") from e

        raw_result = self._model.revoke_access_token(self.access_token)
        account = Account.model_validate(raw_result)
        if account.access_token:
            self.access_token = account.access_token  # Update stored token
        return account

    # --- Page Services ---

    def create_page(
        self,
        title: str,
        content: dict[str, Any],
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

        raw_result = self._model.create_page(
            access_token=self.access_token,
            title=title,
            content=content,
            author_name=author_name,
            author_url=author_url,
            return_content=return_content,
        )
        return Page.model_validate(raw_result)

    def edit_page(
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

        raw_result = self._model.edit_page(
            access_token=self.access_token,
            path=path,
            title=title,
            content_json=content_json,
            author_name=author_name,
            author_url=author_url,
            return_content=return_content,
        )
        return Page.model_validate(raw_result)

    def get_page(self, path: str, return_content: bool = True) -> Page:
        """
        Gets a Telegraph page. Does not require an access token.
        """
        raw_result = self._model.get_page(path, return_content)
        print(raw_result)
        return Page.model_validate(raw_result)

    def get_page_list(self, offset: int = 0, limit: int = 50) -> PageList:
        """
        Gets a list of pages belonging to the Telegraph account associated
        with the current access_token.
        Requires access_token to be set on the service instance.
        """
        try:
            assert self.access_token is not None
        except AssertionError as e:
            raise ValueError("Access token is not set.") from e

        raw_result = self._model.get_page_list(self.access_token, offset, limit)
        return PageList.model_validate(raw_result)

    def get_views(
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
        raw_result = self._model.get_views(path, year, month, day, hour)
        return PageViews.model_validate(raw_result)
