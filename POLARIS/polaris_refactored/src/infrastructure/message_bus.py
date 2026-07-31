"""
POLARIS Message Bus Implementation

Provides message bus functionality for inter-component communication.
This is a simplified implementation for the SWIM system demo.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Message:
    """Represents a message in the message bus."""
    topic: str
    payload: Dict[str, Any]
    timestamp: datetime
    message_id: str
    correlation_id: Optional[str] = None


class PolarisMessageBus:
    """
    Simple in-memory message bus implementation.
    
    In a production system, this would be backed by NATS, Redis, or similar.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._subscribers: Dict[str, List[Callable]] = {}
        self._running = False
        # _connected reflects whether the message bus is logically connected/available
        self._connected = False
        self._message_queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the message bus."""
        if self._running:
            return
        
        self._running = True
        self._connected = True
        self._worker_task = asyncio.create_task(self._message_worker())
        self.logger.info("Message bus started")
    
    async def stop(self) -> None:
        """Stop the message bus."""
        if not self._running:
            return
        
        self._running = False
        self._connected = False
        
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Message bus stopped")

    @property
    def is_connected(self) -> bool:
        """Return whether the message bus is connected/available."""
        return getattr(self, '_connected', False)
    
    async def publish(self, topic: str, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Publish a message to a topic."""
        if not self._running:
            self.logger.warning("Message bus not running, dropping message")
            return
        
        message = Message(
            topic=topic,
            payload=payload,
            timestamp=datetime.now(timezone.utc),
            message_id=f"{topic}_{int(datetime.now().timestamp() * 1000)}",
            correlation_id=correlation_id
        )
        
        await self._message_queue.put(message)
        self.logger.debug(f"Published message to topic: {topic}")
    
    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Subscribe to a topic."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        
        self._subscribers[topic].append(handler)
        self.logger.debug(f"Subscribed to topic: {topic}")
    
    def unsubscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Unsubscribe from a topic."""
        if topic in self._subscribers:
            try:
                self._subscribers[topic].remove(handler)
                if not self._subscribers[topic]:
                    del self._subscribers[topic]
                self.logger.debug(f"Unsubscribed from topic: {topic}")
            except ValueError:
                self.logger.warning(f"Handler not found for topic: {topic}")
    
    async def _message_worker(self) -> None:
        """Worker task to process messages."""
        while self._running:
            try:
                # Wait for message with timeout
                message = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
                
                # Deliver to subscribers
                if message.topic in self._subscribers:
                    for handler in self._subscribers[message.topic]:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(message)
                            else:
                                handler(message)
                        except Exception as e:
                            self.logger.error(f"Error in message handler: {e}", exc_info=True)
                
            except asyncio.TimeoutError:
                continue  # Normal timeout, continue loop
            except Exception as e:
                self.logger.error(f"Error in message worker: {e}", exc_info=True)