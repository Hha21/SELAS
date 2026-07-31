"""Enhanced NATS Client for POLARIS Framework.

Provides a robust NATS client with automatic reconnection,
error handling, and common messaging patterns.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, Optional
from nats.aio.client import Client as NATS
from nats.aio.msg import Msg

from polaris.common.utils import jittered_backoff


# ----------------------------- NATS Client -----------------------------

class NATSClient:
    """Enhanced NATS client with automatic reconnection and error handling.
    
    This client provides:
    - Automatic reconnection with exponential backoff
    - Connection state management
    - Structured logging
    - Common publish/subscribe patterns
    - Request/reply support
    """
    
    def __init__(
        self,
        nats_url: str,
        logger: Optional[logging.Logger] = None,
        name: str = "polaris-client",
        max_reconnect_attempts: int = 10,
        reconnect_base_delay: float = 1.0,
        reconnect_max_delay: float = 60.0,
    ):
        """Initialize NATS client.
        
        Args:
            nats_url: NATS server URL (e.g., "nats://localhost:4222")
            logger: Logger instance for structured logging
            name: Client name for identification
            max_reconnect_attempts: Maximum reconnection attempts
            reconnect_base_delay: Base delay for reconnection backoff
            reconnect_max_delay: Maximum delay for reconnection backoff
        """
        self.nats_url = nats_url
        self.logger = logger or logging.getLogger(__name__)
        self.name = name
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_base_delay = reconnect_base_delay
        self.reconnect_max_delay = reconnect_max_delay
        
        self.nc: Optional[NATS] = None
        self._is_connected = False
        self._connect_lock = asyncio.Lock()
        self._subscriptions: Dict[str, int] = {}  # subject -> subscription_id
        
    @property
    def is_connected(self) -> bool:
        """Check if client is connected to NATS."""
        return self._is_connected and self.nc is not None and self.nc.is_connected
    
    async def connect(self) -> None:
        """Connect to NATS server with automatic retry.
        
        Raises:
            Exception: If connection fails after max attempts
        """
        async with self._connect_lock:
            if self.is_connected:
                self.logger.debug("Already connected to NATS", extra={"url": self.nats_url})
                return
            
            attempt = 0
            last_error = None
            
            while attempt < self.max_reconnect_attempts:
                try:
                    # Create new client if needed
                    if self.nc is None:
                        self.nc = NATS()
                    
                    # Define callbacks
                    async def error_cb(e):
                        self.logger.error("NATS error", extra={"error": str(e)})
                    
                    async def disconnected_cb():
                        self.logger.warning("NATS disconnected")
                        self._is_connected = False
                    
                    async def reconnected_cb():
                        self.logger.info("NATS reconnected")
                        self._is_connected = True
                    
                    async def closed_cb():
                        self.logger.info("NATS connection closed")
                        self._is_connected = False
                    
                    # Connect with callbacks
                    await self.nc.connect(
                        servers=[self.nats_url],
                        name=self.name,
                        error_cb=error_cb,
                        disconnected_cb=disconnected_cb,
                        reconnected_cb=reconnected_cb,
                        closed_cb=closed_cb,
                        max_reconnect_attempts=self.max_reconnect_attempts,
                        reconnect_time_wait=self.reconnect_base_delay,
                    )
                    
                    self._is_connected = True
                    self.logger.info(
                        "NATS connected successfully",
                        extra={
                            "url": self.nats_url,
                            "client_name": self.name,
                            "attempt": attempt
                        }
                    )
                    return
                    
                except Exception as e:
                    last_error = e
                    self._is_connected = False
                    
                    # Clean up failed connection
                    if self.nc:
                        try:
                            await self.nc.close()
                        except Exception:
                            pass
                        self.nc = None
                    
                    if attempt >= self.max_reconnect_attempts - 1:
                        self.logger.error(
                            "Failed to connect to NATS after max attempts",
                            extra={
                                "url": self.nats_url,
                                "attempts": attempt + 1,
                                "error": str(e)
                            }
                        )
                        raise Exception(f"Failed to connect to NATS: {last_error}")
                    
                    delay = jittered_backoff(
                        attempt,
                        self.reconnect_base_delay,
                        self.reconnect_max_delay
                    )
                    
                    self.logger.warning(
                        "NATS connection attempt failed, retrying",
                        extra={
                            "attempt": attempt,
                            "retry_in_sec": round(delay, 2),
                            "error": str(e)
                        }
                    )
                    
                    await asyncio.sleep(delay)
                    attempt += 1
    
    async def ensure_connected(self) -> None:
        """Ensure client is connected, reconnecting if necessary."""
        if not self.is_connected:
            await self.connect()
    
    async def publish(
        self,
        subject: str,
        payload: bytes,
        reply: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> None:
        """Publish message to a subject.
        
        Args:
            subject: Subject to publish to
            payload: Message payload as bytes
            reply: Optional reply subject
            headers: Optional message headers
        
        Raises:
            Exception: If not connected or publish fails
        """
        await self.ensure_connected()
        
        try:
            await self.nc.publish(subject, payload, reply=reply, headers=headers)
            self.logger.debug(
                "Message published",
                extra={
                    "subject": subject,
                    "payload_size": len(payload),
                    "has_reply": reply is not None
                }
            )
        except Exception as e:
            self.logger.error(
                "Failed to publish message",
                extra={
                    "subject": subject,
                    "error": str(e)
                }
            )
            raise
    
    async def publish_json(
        self,
        subject: str,
        data: Any,
        reply: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> None:
        """Publish JSON-encoded message.
        
        Args:
            subject: Subject to publish to
            data: Data to JSON-encode and publish
            reply: Optional reply subject
            headers: Optional message headers
        """
        try:
            payload = json.dumps(data).encode()
            await self.publish(subject, payload, reply=reply, headers=headers)
        except (json.JSONEncodeError, TypeError, ValueError) as e:
            self.logger.error(
                "Failed to encode JSON",
                extra={"error": str(e)}
            )
            raise
    
    async def subscribe(
        self,
        subject: str,
        callback: Callable[[Msg], None],
        queue: Optional[str] = None
    ) -> int:
        """Subscribe to a subject.
        
        Args:
            subject: Subject pattern to subscribe to
            callback: Async callback function for messages
            queue: Optional queue group name
        
        Returns:
            Subscription ID
        
        Raises:
            Exception: If not connected or subscription fails
        """
        await self.ensure_connected()
        
        try:
            sid = await self.nc.subscribe(subject, cb=callback, queue=queue)
            self._subscriptions[subject] = sid
            
            self.logger.info(
                "Subscribed to subject",
                extra={
                    "subject": subject,
                    "sid": sid,
                    "queue": queue
                }
            )
            
            return sid
            
        except Exception as e:
            self.logger.error(
                "Failed to subscribe",
                extra={
                    "subject": subject,
                    "error": str(e)
                }
            )
            raise
    
    async def unsubscribe(self, sid: int) -> None:
        """Unsubscribe from a subscription.
        
        Args:
            sid: Subscription ID to unsubscribe
        """
        if not self.is_connected:
            return
        
        try:
            await self.nc.unsubscribe(sid)
            # Remove from tracking
            self._subscriptions = {
                k: v for k, v in self._subscriptions.items() if v != sid
            }
            self.logger.info("Unsubscribed", extra={"sid": sid})
        except Exception as e:
            self.logger.error(
                "Failed to unsubscribe",
                extra={"sid": sid, "error": str(e)}
            )
    
    async def request(
        self,
        subject: str,
        payload: bytes,
        timeout: float = 1.0
    ) -> Msg:
        """Send request and wait for reply.
        
        Args:
            subject: Subject to send request to
            payload: Request payload
            timeout: Timeout in seconds
        
        Returns:
            Reply message
        
        Raises:
            asyncio.TimeoutError: If no reply within timeout
            Exception: If not connected or request fails
        """
        await self.ensure_connected()
        
        try:
            msg = await self.nc.request(subject, payload, timeout=timeout)
            self.logger.debug(
                "Request completed",
                extra={
                    "subject": subject,
                    "reply_size": len(msg.data) if msg else 0
                }
            )
            return msg
        except asyncio.TimeoutError:
            self.logger.warning(
                "Request timeout",
                extra={"subject": subject, "timeout": timeout}
            )
            raise
        except Exception as e:
            self.logger.error(
                "Request failed",
                extra={"subject": subject, "error": str(e)}
            )
            raise
    
    async def request_json(
        self,
        subject: str,
        data: Any,
        timeout: float = 1.0
    ) -> Any:
        """Send JSON request and parse JSON reply.
        
        Args:
            subject: Subject to send request to
            data: Data to JSON-encode and send
            timeout: Timeout in seconds
        
        Returns:
            Parsed JSON reply data
        """
        payload = json.dumps(data).encode()
        msg = await self.request(subject, payload, timeout)
        return json.loads(msg.data.decode())
    
    async def close(self) -> None:
        """Close NATS connection gracefully."""
        if self.nc:
            try:
                # Unsubscribe all
                for sid in self._subscriptions.values():
                    try:
                        await self.nc.unsubscribe(sid)
                    except Exception:
                        pass
                self._subscriptions.clear()
                
                # Drain and close
                await self.nc.drain()
                await self.nc.close()
                
                self.logger.info("NATS connection closed")
            except Exception as e:
                self.logger.error(
                    "Error closing NATS connection",
                    extra={"error": str(e)}
                )
            finally:
                self._is_connected = False
                self.nc = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

