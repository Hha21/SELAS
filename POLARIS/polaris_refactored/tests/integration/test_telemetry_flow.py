import asyncio
from datetime import datetime, timezone
import pytest

from polaris_refactored.src.framework.events import PolarisEventBus, TelemetryEvent
from polaris_refactored.src.digital_twin.telemetry_subscriber import subscribe_telemetry_persistence
from polaris_refactored.src.digital_twin.knowledge_base import PolarisKnowledgeBase
from polaris_refactored.src.infrastructure.data_storage.data_store import PolarisDataStore
from polaris_refactored.src.infrastructure.data_storage.storage_backend import InMemoryGraphStorageBackend
from polaris_refactored.src.domain.models import SystemState, MetricValue, HealthStatus


@pytest.mark.asyncio
async def test_telemetry_event_persists_to_knowledge_base():
    # Arrange event bus and data store
    event_bus = PolarisEventBus(worker_count=1)
    backend = InMemoryGraphStorageBackend()
    data_store = PolarisDataStore({
        "document": backend,
        "graph": backend,
        "time_series": backend,
    })
    await data_store.start()
    kb = PolarisKnowledgeBase(data_store)

    await event_bus.start()
    await subscribe_telemetry_persistence(event_bus, kb)

    # Create telemetry
    metrics = {
        "cpu": MetricValue(name="cpu", value=0.7, unit="pct"),
        "latency": MetricValue(name="latency", value=123.0, unit="ms"),
    }
    state = SystemState(
        system_id="svc-A",
        timestamp=datetime.now(timezone.utc),
        metrics=metrics,
        health_status=HealthStatus.HEALTHY,
    )
    event = TelemetryEvent(system_state=state)

    # Act: publish and allow worker to process
    await event_bus.publish(event)
    await asyncio.sleep(0.05)

    # Assert: KB persisted state and can retrieve as current
    latest = await kb.get_current_state("svc-A")
    assert latest is not None
    assert latest.system_id == "svc-A"
    assert "cpu" in latest.metrics and latest.metrics["cpu"].unit == "pct"

    # Cleanup
    await event_bus.stop()
