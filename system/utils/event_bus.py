import asyncio
import logging
from typing import Callable, Hashable

logger = logging.getLogger(__name__)


class EventBus:
    """
    Simple event bus for asynchronous event handling
    Allows components to publish and subscribe to events without direct coupling
    """

    def __init__(self):
        self._handlers: dict[Hashable, list[Callable]] = {}

    def subscribe(self, event: Hashable, handler: Callable) -> None:
        """
        Subscribe to an event

        Args:
            event: The event to subscribe to
            handler: Callback function or coroutine to handle the event
        """
        if event not in self._handlers:
            self._handlers[event] = []

        if handler not in self._handlers[event]:
            self._handlers[event].append(handler)
            logger.debug(f"Subscribed to event '{event}'")

    def unsubscribe(self, event: Hashable, handler: Callable) -> None:
        """
        Unsubscribe from an event

        Args:
            event: The event to unsubscribe from
            handler: Callback function to remove
        """
        if event in self._handlers and handler in self._handlers[event]:
            self._handlers[event].remove(handler)
            logger.debug(f"Unsubscribed from event '{event}'")

    def publish(self, event: Hashable, *args, **kwargs) -> None:
        """
        Publish a synchronous event

        Args:
            event: The event to publish
            *args: Positional arguments to pass to handlers
            **kwargs: Keyword arguments to pass to handlers
        """
        if event not in self._handlers:
            return

        for handler in self._handlers[event]:
            try:
                handler(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in event handler for '{event}': {e}")
                raise e

    async def publish_async(self, event: Hashable, *args, **kwargs) -> None:
        """
        Publish an asynchronous event

        Args:
            event: The event to publish
            *args: Positional arguments to pass to handlers
            **kwargs: Keyword arguments to pass to handlers
        """
        if event not in self._handlers:
            return

        # Create tasks for all coroutine handlers
        tasks = []
        for handler in self._handlers[event]:
            try:
                if asyncio.iscoroutinefunction(handler):
                    # Create task for coroutine function
                    task = asyncio.create_task(handler(*args, **kwargs))
                    tasks.append(task)
                else:
                    # Call synchronous handlers directly
                    handler(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in event handler for '{event}': {e}")

        # Wait for all async handlers to complete if there are any
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


# Global event bus instance
event_bus = EventBus()
