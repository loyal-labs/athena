import json
from typing import Any

import requests

from src.telegraph.telegraph_exceptions import TelegraphAPIError


class TelegraphModel:
    """
    Handles raw interactions with the Telegraph API endpoints.
    Returns raw dictionary data from the 'result' field or raises TelegraphAPIError.
    """

    BASE_URL = "https://api.telegra.ph"

    def _request(
        self,
        method_name: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        path_param: str | None = None,
        http_method: str = "GET",
    ) -> dict[str, Any]:
        """
        Internal helper to make requests to the Telegraph API.

        Args:
            method_name: The API method (e.g., "createAccount").
            params: URL parameters for GET requests.
            data: Data payload for POST requests.
            path_param: Optional path parameter (e.g., page path).
            http_method: "GET" or "POST".

        Returns:
            The raw dictionary from the 'result' field of the JSON response.

        Raises:
            TelegraphAPIError: If the API returns ok=false or a request fails.
            requests.exceptions.RequestException: For network/HTTP errors.
        """
        url = f"{self.BASE_URL}/{method_name}"
        if path_param:
            url += f"/{path_param}"

        try:
            if http_method == "POST":
                response = requests.post(url, data=data)
            else:  # Default to GET
                response = requests.get(url, params=params)

            response.raise_for_status()

            try:
                response_data = response.json()
            except json.JSONDecodeError as e:
                raise TelegraphAPIError(
                    f"Failed to decode JSON response: {response.text}"
                ) from e

            if response_data.get("ok"):
                return response_data.get(
                    "result", {}
                )  # Return result or empty dict if missing
            else:
                error_msg = response_data.get("error", "Unknown API error")
                raise TelegraphAPIError(error_msg)

        except requests.exceptions.RequestException as e:
            # Re-raise network/HTTP errors for potential higher-level handling
            raise TelegraphAPIError(f"Network or HTTP error: {e}") from e

    # --- Account Methods ---

    def create_account(
        self,
        short_name: str,
        author_name: str | None = None,
        author_url: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "short_name": short_name,
            "author_name": author_name,
            "author_url": author_url,
        }
        # Filter out None values
        params = {k: v for k, v in params.items() if v is not None}
        return self._request(
            "createAccount", params=params, http_method="GET"
        )  # Or POST

    def edit_account_info(
        self,
        access_token: str,
        short_name: str | None = None,
        author_name: str | None = None,
        author_url: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "access_token": access_token,
            "short_name": short_name,
            "author_name": author_name,
            "author_url": author_url,
        }
        params = {k: v for k, v in params.items() if v is not None}
        return self._request(
            "editAccountInfo", params=params, http_method="GET"
        )  # Or POST

    def get_account_info(
        self, access_token: str, fields: list[str] | None = None
    ) -> dict[str, Any]:
        params = {"access_token": access_token}
        if fields:
            # API expects fields as a JSON array string
            params["fields"] = json.dumps(fields)
        return self._request("getAccountInfo", params=params, http_method="GET")

    def revoke_access_token(self, access_token: str) -> dict[str, Any]:
        params = {"access_token": access_token}
        return self._request("revokeAccessToken", params=params, http_method="GET")

    # --- Page Methods ---

    def create_page(
        self,
        access_token: str,
        title: str,
        content_json: str,  # Expect pre-formatted JSON string
        author_name: str | None = None,
        author_url: str | None = None,
        return_content: bool = False,
    ) -> dict[str, Any]:
        data = {
            "access_token": access_token,
            "title": title,
            "content": content_json,
            "author_name": author_name,
            "author_url": author_url,
            "return_content": return_content,
        }
        data = {
            k: v for k, v in data.items() if v is not None and v is not False
        }  # Keep False for return_content if explicitly set
        if "return_content" in data:
            data["return_content"] = str(data["return_content"]).lower()

        # Using POST is safer for potentially large content
        return self._request("createPage", data=data, http_method="POST")

    def edit_page(
        self,
        access_token: str,
        path: str,
        title: str,
        content_json: str,  # Expect pre-formatted JSON string
        author_name: str | None = None,
        author_url: str | None = None,
        return_content: bool = False,
    ) -> dict[str, Any]:
        data = {
            "access_token": access_token,
            "title": title,
            "content": content_json,
            "author_name": author_name,
            "author_url": author_url,
            "return_content": return_content,
        }
        data = {k: v for k, v in data.items() if v is not None and v is not False}
        if "return_content" in data:
            data["return_content"] = str(data["return_content"]).lower()

        # Using POST is safer for potentially large content
        return self._request("editPage", path_param=path, data=data, http_method="POST")

    def get_page(self, path: str, return_content: bool = False) -> dict[str, Any]:
        params = {"return_content": str(return_content).lower()}
        return self._request(
            "getPage", path_param=path, params=params, http_method="GET"
        )

    def get_page_list(
        self, access_token: str, offset: int = 0, limit: int = 50
    ) -> dict[str, Any]:
        params = {
            "access_token": access_token,
            "offset": offset,
            "limit": limit,
        }
        return self._request("getPageList", params=params, http_method="GET")

    def get_views(
        self,
        path: str,
        year: int | None = None,
        month: int | None = None,
        day: int | None = None,
        hour: int | None = None,
    ) -> dict[str, Any]:
        params = {
            "year": year,
            "month": month,
            "day": day,
            "hour": hour,
        }
        params = {k: v for k, v in params.items() if v is not None}
        return self._request(
            "getViews", path_param=path, params=params, http_method="GET"
        )
