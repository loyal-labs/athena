from enum import Enum
from typing import Union

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, computed_field

from src.shared.config import BaseConfig


# --- Config ---
class TelegraphConfig(BaseConfig):
    # --- Constants ---
    author_name: str = "Loyal Athena"
    short_name: str = "Loyal Athena"
    author_url: str = "https://t.me/athena_tgbot"

    # for Google App Engine
    access_token_secret_id: str | None = Field(
        None, validation_alias="TELEGRAPH_ACCESS_TOKEN_SECRET_ID"
    )

    # for local dev
    access_token_local_var: str = "TELEGRAPH_ACCESS_TOKEN"

    class Config(BaseConfig.Config):
        env_prefix = "TELEGRAPH_"

    @computed_field(return_type=str)
    @property
    def access_token(self) -> str:
        return self._resolve_secret(
            self.access_token_local_var, self.access_token_secret_id
        )


# --- Node Handling ---
Node = Union[str, "NodeElement"]


class NodeElement(BaseModel):
    """
    Represents a DOM element node.
    Ref: https://telegra.ph/api#NodeElement
    """

    model_config = ConfigDict(extra="ignore")  # Ignore extra fields API might send

    tag: str = Field(
        ..., description="Name of the DOM element (e.g., 'p', 'a', 'iframe')."
    )
    attrs: dict[str, str] | None = Field(
        None,
        description="Attributes of the DOM element ({'href': '...', 'src': '...'}).",
    )
    children: list[Node] | None = Field(
        None, description="List of child nodes (strings or NodeElements)."
    )


# --- API Object Schemas ---
class Account(BaseModel):
    """
    Represents a Telegraph account.
    Ref: https://telegra.ph/api#Account
    """

    model_config = ConfigDict(extra="ignore")

    short_name: str = Field(..., description="Account name.")
    author_name: str | None = Field(None, description="Default author name.")
    author_url: HttpUrl | str | None = Field(
        None, description="Default author URL."
    )  # Can be any string, but often a URL
    access_token: str | None = Field(
        None, description="Only returned by createAccount and revokeAccessToken."
    )
    auth_url: HttpUrl | None = Field(None, description="URL to authorize a browser.")
    page_count: int | None = Field(
        None, description="Number of pages belonging to the account."
    )


class Page(BaseModel):
    """
    Represents a page on Telegraph.
    Ref: https://telegra.ph/api#Page
    """

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Path to the page.")
    url: HttpUrl = Field(..., description="URL of the page.")
    title: str = Field(..., description="Title of the page.")
    description: str | None = Field(
        None, description="Description of the page."
    )  # Often derived from content
    author_name: str | None = Field(None, description="Name of the author.")
    author_url: HttpUrl | str | None = Field(
        None, description="Profile link of the author."
    )
    image_url: HttpUrl | None = Field(None, description="Image URL of the page.")
    content: list[Node] | None = Field(
        None, description="Content of the page (returned when return_content=true)."
    )
    views: int = Field(..., description="Number of page views.")
    can_edit: bool | None = Field(
        None,
        description="True if the account can edit the page (requires access_token).",
    )


class PageList(BaseModel):
    """
    Represents a list of Telegraph articles belonging to an account.
    Ref: https://telegra.ph/api#PageList
    """

    model_config = ConfigDict(extra="ignore")

    total_count: int = Field(
        ..., description="Total number of pages belonging to the account."
    )
    pages: list[Page] = Field(..., description="Requested pages.")


class PageViews(BaseModel):
    """
    Represents the number of page views for a Telegraph article.
    Ref: https://telegra.ph/api#PageViews
    """

    model_config = ConfigDict(extra="ignore")

    views: int = Field(..., description="Number of page views for the target page.")


# --- Telegraph Utils ---
class OutputFormat(str, Enum):
    HTML_STRING = "html_string"
    JSON_STRING = "json_string"
    PYTHON_LIST = "python_list"
