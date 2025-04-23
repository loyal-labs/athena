import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel

from src.shared.events import EventPayload
from src.telemetree.posts.posts_constants import OFFSET_DAYS, POST_LIMIT

logger = logging.getLogger("athena.telemetree.posts")

"""
AGENTS
"""


@dataclass
class Output:
    response: str


"""
PAYLOAD
"""


class GetChannelPostsPayload(EventPayload):
    """
    A payload for getting channel posts
    """

    group_username: str
    limit: int = POST_LIMIT
    offset_days: int = OFFSET_DAYS


"""
DATA MODEL
"""


class ChannelPost(BaseModel):
    """
    A post from a channel
    """

    date: datetime
    text: str
    msg_url: str

    @classmethod
    def from_telemetree_response(cls, response: dict[str, Any]) -> Self:
        """
        Create a ChannelPost from a telemetree response
        """
        try:
            assert response
            assert response["message"]
        except AssertionError as e:
            logger.exception("Error creating ChannelPost from telemetree response")
            raise e
        except Exception as e:
            logger.exception("Error creating ChannelPost from telemetree response")
            raise e

        message_data = response["message"]
        return cls(
            date=message_data["date"],
            text=message_data["text"],
            msg_url=message_data["message_url"],
        )


"""
EVENT PAYLOADS
"""


class NewsPostsInputPayload(EventPayload):
    query: str
