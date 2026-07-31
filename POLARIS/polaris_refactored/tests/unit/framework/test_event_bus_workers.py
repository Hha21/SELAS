import asyncio
import pytest

from polaris_refactored.src.framework.events import (
    PolarisEventBus,
    PolarisEvent,
    EventMetadata,
)


class DummyEvent(PolarisEvent):
    def __init__(self, name: str, **kwargs):
        super().__init__(**kwargs)
        self.name = name


@pytest.mark.asyncio
async def test_event_bus_concurrency_two_workers_process_multiple_events():
    bus = PolarisEventBus(worker_count=2)
    await bus.start()

    processed = []

    async def handler(evt: PolarisEvent):
        # Simulate some work
        await asyncio.sleep(0.02)
        processed.append(evt.name)

    # Subscribe generic callable to DummyEvent
    sub_id = bus.subscribe(DummyEvent, handler)

    # Publish a batch of events
    for i in range(6):
        await bus.publish(DummyEvent(name=f"e{i}"))

    # Wait for processing (2 workers should finish quickly)
    for _ in range(20):
        if len(processed) >= 6:
            break
        await asyncio.sleep(0.02)

    await bus.stop()

    assert sorted(processed) == [f"e{i}" for i in range(6)]


@pytest.mark.asyncio
async def test_event_bus_retry_logic_requeues_until_success():
    bus = PolarisEventBus(worker_count=1)
    await bus.start()

    attempts = {"count": 0}

    async def flaky_handler(evt: PolarisEvent):
        attempts["count"] += 1
        # Fail twice, succeed third time
        if attempts["count"] < 3:
            raise RuntimeError("transient")
        # success
        return None

    # Subscribe handler
    sub_id = bus.subscribe(DummyEvent, flaky_handler)

    evt = DummyEvent(name="retry_me", metadata=EventMetadata(max_retries=3))
    await bus.publish(evt)

    # Wait until processed (should require retries)
    for _ in range(50):
        stats = bus.get_processing_stats()
        if stats["events_processed"] >= 1 and attempts["count"] >= 3:
            break
        await asyncio.sleep(0.02)

    await bus.stop()

    assert attempts["count"] == 3
