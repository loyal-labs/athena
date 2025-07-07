import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel
from pyrogram.types import Message

logger = logging.getLogger("athena.telegram.messages.schemas")

"""
AGENTS
"""


@dataclass
class ResponseDependencies:
    last_messages: list["GramMessage"]
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
            logger.error("Message: %s", message)
            logger.error("Message %s has no text, from_user, or date", message.id)
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
