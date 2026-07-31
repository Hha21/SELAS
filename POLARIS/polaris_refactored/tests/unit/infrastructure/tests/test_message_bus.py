import asyncio
import json
import pytest
from datetime import datetime, timezone

from polaris_refactored.src.infrastructure.message_bus import (
    PolarisMessageBus,
    LoggingMiddleware,
    MetricsMiddleware,
)
from polaris_refactored.src.domain.interfaces import EventHandler


class _CaptureHandler(EventHandler):
    def __init__(self, predicate=lambda e: True):
        self.events = []
        self._predicate = predicate

    async def handle(self, event):
        self.events.append(event)

    def can_handle(self, event):
        return self._predicate(event)


@pytest.mark.asyncio
async def test_publish_raises_when_disconnected(fake_broker):
    bus = PolarisMessageBus(fake_broker)
    with pytest.raises(Exception):
        await bus.publish("topic.a", {"x": 1})


@pytest.mark.asyncio
async def test_subscribe_requires_connection(fake_broker):
    bus = PolarisMessageBus(fake_broker)
    handler = _CaptureHandler()
    with pytest.raises(Exception):
        await bus.subscribe("t1", handler)


@pytest.mark.asyncio
async def test_publish_subscribe_delivers_and_middleware_order(fake_broker, metrics_collector, caplog):
    # Arrange middleware
    logger = _DummyLogger()
    mlog = LoggingMiddleware(logger)
    mmet = MetricsMiddleware(metrics_collector)
    bus = PolarisMessageBus(fake_broker, middleware_chain=None)
    # Manually set chain order: logging then metrics
    bus.middleware_chain.middleware_list = [mlog, mmet]

    await bus.start()

    handler_all = _CaptureHandler()
    await bus.subscribe("telemetry", handler_all)

    # Act: publish an event object with datetime and nested object
    class Payload:
        def __init__(self):
            self.when = datetime(2023, 1, 2, 3, 4, 5)
            self.nested = type("N", (), {"k": 1})()

    await bus.publish("telemetry", Payload())

    # Allow loop to deliver
    await asyncio.sleep(0)

    # Assert handler received deserialized event
    assert len(handler_all.events) == 1
    ev = handler_all.events[0]
    # GenericEvent reconstructed should have attributes from Payload
    assert hasattr(ev, "when") and hasattr(ev, "nested")
    # LoggingMiddleware should have recorded debug calls; Metrics collected
    assert metrics_collector.counters.get("messages_published_total", 0) == 1
    assert metrics_collector.counters.get("messages_received_total", 0) == 1

    await bus.stop()


@pytest.mark.asyncio
async def test_multiple_handlers_and_unsubscribe_cleanup(fake_broker):
    bus = PolarisMessageBus(fake_broker)
    await bus.start()

    h1 = _CaptureHandler()
    h2 = _CaptureHandler()
    await bus.subscribe("t.multi", h1)
    await bus.subscribe("t.multi", h2)

    # publish once
    class E: pass
    await bus.publish("t.multi", E())
    await asyncio.sleep(0)

    assert len(h1.events) == 1 and len(h2.events) == 1

    # Unsubscribe only h1: broker subscription remains since h2 still present
    await bus.unsubscribe("t.multi", h1)
    await bus.publish("t.multi", E())
    await asyncio.sleep(0)
    assert len(h1.events) == 1 and len(h2.events) == 2

    # Unsubscribe h2: broker unsubscribed by bus internally
    await bus.unsubscribe("t.multi", h2)
    # publish again should not be delivered to any
    await bus.publish("t.multi", E())
    await asyncio.sleep(0)
    assert len(h2.events) == 2

    await bus.stop()


@pytest.mark.asyncio
async def test_can_handle_filters_events(fake_broker):
    bus = PolarisMessageBus(fake_broker)
    await bus.start()

    h_only_x = _CaptureHandler(lambda e: hasattr(e, "x"))
    await bus.subscribe("t.f", h_only_x)

    class A: pass
    class B:
        def __init__(self):
            self.x = 1

    await bus.publish("t.f", A())
    await bus.publish("t.f", B())
    await asyncio.sleep(0)

    assert len(h_only_x.events) == 1

    await bus.stop()


class _DummyLogger:
    def debug(self, *_args, **_kwargs):
        pass
