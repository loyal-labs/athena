"""
Events are used to communicate between different parts of the application.

They are published to the event bus and subscribed to by the event bus.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventPayload(BaseModel):
    class Config:
        arbitrary_types_allowed = True


class Event(BaseModel):
    topic: str
    payload: dict[str, Any] | EventPayload | None = None
    timestamp: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_dict(
        cls, topic: str | Enum, payload: dict[str, Any] | EventPayload | None = None
    ) -> "Event":
        if isinstance(topic, Enum):
            topic = str(topic.value)
        else:
            topic = str(topic)

        return cls(topic=topic, payload=payload)

    @classmethod
    def extract_payload(
        cls, event: "Event", payload_type: type[EventPayload]
    ) -> EventPayload:
        if not isinstance(event.payload, payload_type):
            payload = payload_type(**event.payload)  # type: ignore
        else:
            payload = event.payload
        return payload
