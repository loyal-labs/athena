from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ChatTypes(str, Enum):
    """
    Chat types are the types of chats that can be summarized.
    """

    PERSONAL = "personal"
    GROUP = "group"
    CHANNEL = "channel"

    @classmethod
    def from_telegram_type(cls, telegram_type: str) -> "ChatTypes":
        """Convert Telegram chat type to API chat type."""
        try:
            return cls(telegram_type.lower())
        except ValueError:
            return cls.GROUP


class Entity(BaseModel):
    """
    Entity is a user or a chat.

    Parameters:
        name: Name of the entity
        profile_picture: URL of the profile picture of the entity
    """

    name: str = Field(..., description="Name of the entity")
    profile_picture: str = Field(..., description="Base64 encoded profile picture")


class ChatSummaryPoint(Entity):
    """
    Chat summary point is a user and their summary of the topic.

    Parameters:
        name: Name of the user
        profile_picture: URL of the profile picture of the user
        summary: Summary of user interactions
    """

    summary: str = Field(..., description="Summary of user interactions")


class ChatSummaryTopic(BaseModel):
    """
    Chat summary topic is a list of points.
    Each point is a user and their summary of the topic.

    Parameters:
        topic: Topic of the conversation
        date: Date of the conversation
        points: List of points
    """

    topic: str = Field(..., description="Topic of the chat")
    date: datetime = Field(..., description="Date of the topic")
    points: list[ChatSummaryPoint] = Field(..., description="Points made by users")


class ChatSummary(Entity):
    """
    Chat summary is a list of topics, each topic is a list of points.
    Each point is a user and their summary of the topic.

    Parameters:
        name: Name of the chat
        profile_picture: URL of the profile picture of the chat
        chat_type: Type of the chat
        topics: List of topics
    """

    chat_type: ChatTypes = Field(..., description="Chat type")
    topics: list[ChatSummaryTopic] = Field(..., description="Topics of the chat")


class ChatSummaryResponse(BaseModel):
    """
    Chat summary response is a list of chats.
    """

    total_chats: int = Field(..., description="Total chats with unread messages")
    selected_chats: list[int] = Field(..., description="Selected chats")
    chats: list[ChatSummary] = Field(..., description="Chats")


class MarkAsReadRequest(BaseModel):
    """
    Mark as read request is a request to mark a chat as read.
    """

    chat_id: int = Field(..., description="Chat ID")
    max_id: int | None = Field(None, description="Max ID")
