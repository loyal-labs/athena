import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel
from pyrogram.client import Client
from pyrogram.types import Message

from src.shared.event_bus import EventBus
from src.shared.events import EventPayload

logger = logging.getLogger("athena.telegram.messages")

"""
AGENTS
"""


@dataclass
class ResponseDependencies:
    last_messages: list["GramMessage"]
    event_bus: EventBus
    sender: str
    message: Message


@dataclass
class Response(BaseModel):
    text: str


class GramMessage(BaseModel):
    text: str
    sender: str
    date: datetime
    role: Literal["user", "assistant"]

    @classmethod
    def from_pyrogram_message(cls, message: Message) -> Self:
        try:
            assert message.text
            assert message.from_user
            assert message.date
        except AssertionError as e:
            logger.error(f"Message {message.id} has no text, from_user, or date")
            raise e
        except Exception as e:
            logger.exception(
                f"Error creating GramMessage from pyrogram message {message.id}"
            )
            raise e

        return cls(
            text=message.text,
            sender=message.from_user.first_name,
            date=message.date,
            role="assistant" if message.from_user.is_bot else "user",
        )


"""
EVENT PAYLOADS
"""


class RespondToMessagePayload(EventPayload):
    client: Client
    message: Message
