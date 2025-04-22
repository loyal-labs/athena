"""
The event bus is used to communicate between different parts of the application.

It is a singleton that is used to publish and subscribe to events.
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from asyncio import Task, create_task, gather
from collections.abc import Callable, Coroutine
from enum import Enum
from inspect import getmembers, isawaitable, ismethod
from typing import Any, TypeVar

from src.shared.config import SharedConfig
from src.shared.events import Event

logger = logging.getLogger("athena.base-event-bus")

E = TypeVar("E", bound=Event)
R = TypeVar("R", covariant=True)  # Return type
EventHandler = Callable[[E], Any | Coroutine[Any, Any, R]]


class EventBusInterface(ABC):
    @staticmethod
    @abstractmethod
    def subscribe(
        topic: str | Enum,
    ) -> Callable[
        [Callable[..., Any | Coroutine[Any, Any, Any]]],
        Callable[..., Any | Coroutine[Any, Any, Any]],
    ]:
        """Attaches subscription metadata to a method."""
        pass

    @abstractmethod
    async def publish(self, event: Event) -> None:
        """Publish an event"""
        pass

    @abstractmethod
    def subscribe_to_topic(
        self, topic: str, callback: Callable[[E], Any | Coroutine[Any, Any, R]]
    ) -> None:
        """Subscribe to an event type"""
        pass

    @abstractmethod
    def get_subscriber_count(self, topic: str) -> int:
        """Get the number of subscribers for an event type"""
        pass

    @abstractmethod
    async def publish_and_wait(self, event: Event) -> None:
        """Publish an event and wait for all handlers to complete"""
        pass

    @abstractmethod
    def register_subscribers_from(self, obj: object) -> None:
        """Register methods decorated with @subscribe from an object."""
        pass

    @abstractmethod
    async def request(self, topic: Enum, timeout: float = 5.0, **kwargs: Any) -> Any:
        """Send a request event, return the result"""
        pass


class EventBus(EventBusInterface):
    def __init__(self):
        self._subscribers: dict[type[Event], list[EventHandler[Any, Any]]] = {}
        self._topic_subscribers: dict[str, list[EventHandler[Any, Any]]] = {}
        self._event_tasks: dict[str, set[Task[Any]]] = {}

    # Decorator to subscribe a method to an event bus topic
    @staticmethod
    def subscribe(
        topic: str | Enum,
    ) -> Callable[
        [Callable[..., Any | Coroutine[Any, Any, Any]]],
        Callable[..., Any | Coroutine[Any, Any, Any]],
    ]:
        """Attaches subscription metadata to a method."""
        if isinstance(topic, Enum):
            topic = str(topic.value)
        else:
            topic = str(topic)

        def decorator(
            func: Callable[..., Any | Coroutine[Any, Any, Any]],
        ) -> Callable[..., Any | Coroutine[Any, Any, Any]]:
            # Dynamically attach the topic to the function object.
            func._subscribed_topic = topic  # type: ignore[attr-defined]
            return func

        return decorator

    def subscribe_to_topic(
        self, topic: str, callback: Callable[[E], Any | Coroutine[Any, Any, R]]
    ) -> None:
        """Subscribe to all events of a specific topic"""
        if topic not in self._topic_subscribers:
            self._topic_subscribers[topic] = []
        self._topic_subscribers[topic].append(callback)

    async def publish(self, event: Event) -> None:
        """Publish an event to type subscribers and topic subscribers"""
        logger.debug("Publishing event: %s", event)

        # Type-based subscribers
        event_type = type(event)
        handlers = self._subscribers.get(event_type, [])

        # Topic-based subscribers
        topic_handlers = self._topic_subscribers.get(event.topic, [])

        # Combine handlers
        all_handlers = handlers + topic_handlers

        if not all_handlers:
            return

        coros: list[Coroutine[Any, Any, None]] = []
        for handler in all_handlers:
            result = handler(event)
            if isawaitable(result):
                coros.append(result)

        if coros:
            await gather(*coros)

    async def request(self, topic: Enum, timeout: float = 5.0, **kwargs: Any) -> Any:
        """Send a request event, return the result"""
        event_dict = {key: value for key, value in kwargs.items() if value is not None}
        event = Event.from_dict(topic, event_dict)

        event_type = type(event)
        handlers = self._subscribers.get(event_type, [])
        topic_handlers = self._topic_subscribers.get(event.topic, [])
        all_handlers = handlers + topic_handlers

        if not all_handlers:
            raise ValueError(f"No handlers registered for event {event}")

        # Use first handler for request-response
        handler = all_handlers[0]
        result = handler(event)
        if isawaitable(result):
            return await asyncio.wait_for(result, timeout)
        return result

    async def publish_and_wait(self, event: Event) -> None:
        """Publish an event and wait for all handlers to complete"""
        logger.debug("Publishing event and waiting: %s", event)

        # Type-based subscribers
        event_type = type(event)
        handlers = self._subscribers.get(event_type, [])

        # Topic-based subscribers
        topic_handlers = self._topic_subscribers.get(event.topic, [])

        # Combine handlers
        all_handlers = handlers + topic_handlers

        if not all_handlers:
            return

        # Create a unique ID for this event instance
        event_id = str(uuid.uuid4())
        self._event_tasks[event_id] = set()

        # Create tasks for each handler
        for handler in all_handlers:
            logger.debug("Creating task for handler: %s", handler)
            result = handler(event)
            if isawaitable(result):
                task = create_task(result)
                self._event_tasks[event_id].add(task)

        # Wait for all tasks to complete
        if self._event_tasks[event_id]:
            logger.debug("Waiting for %s tasks", len(self._event_tasks[event_id]))
            await gather(*self._event_tasks[event_id])

        # Clean up
        del self._event_tasks[event_id]
        logger.debug("All handlers completed for event: %s", event)

    def get_subscriber_count(self, topic: str) -> int:
        """Get the number of subscribers for an event type"""
        return len(self._topic_subscribers.get(topic, []))

    def register_subscribers_from(self, obj: object) -> None:
        """Register all methods decorated with @subscribe from the given object."""
        for _, method in getmembers(obj, predicate=ismethod):
            if hasattr(method, "_subscribed_topic"):
                topic = getattr(method, "_subscribed_topic")
                self.subscribe_to_topic(topic, method)  # type: ignore
                logger.debug(
                    "Subscribed %s from %s to topic %s",
                    method.__name__,
                    obj.__class__.__name__,
                    topic,
                )


def get_event_bus(config_obj: SharedConfig) -> EventBus | EventBusInterface:
    if config_obj.event_bus == "local":
        return EventBus()
    else:
        raise ValueError(f"Unsupported event bus type: {config_obj.event_bus}")
