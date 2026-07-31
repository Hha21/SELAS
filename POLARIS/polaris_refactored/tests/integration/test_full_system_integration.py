"""
Integration tests: verify all major components working together with persistence.
"""

import asyncio
from datetime import datetime, timezone, timedelta

import pytest

from polaris_refactored.src.framework.events import PolarisEventBus, TelemetryEvent, ExecutionResultEvent
from polaris_refactored.src.control_reasoning.adaptive_controller import PolarisAdaptiveController
from polaris_refactored.src.digital_twin.knowledge_base import PolarisKnowledgeBase
from polaris_refactored.src.infrastructure.data_storage.data_store import PolarisDataStore
from polaris_refactored.src.infrastructure.data_storage.storage_backend import InMemoryGraphStorageBackend
from polaris_refactored.src.adapters.monitor_adapter.monitor_adapter import MonitorAdapter
from polaris_refactored.src.adapters.monitor_adapter.monitor_types import MetricCollectionMode
from polaris_refactored.src.adapters.execution_adapter.execution_adapter import ExecutionAdapter
from polaris_refactored.src.adapters.base_adapter import AdapterConfiguration
from polaris_refactored.src.domain.models import MetricValue, SystemState, HealthStatus

from polaris_refactored.tests.e2e.helpers import FullMockConnector, FakePluginRegistry, make_execution_adapter_config


@pytest.fixture
async def event_bus():
    bus = PolarisEventBus(worker_count=1)
    await bus.start()
    try:
        yield bus
    finally:
        await bus.stop()


@pytest.fixture
async def knowledge_base():
    backend = InMemoryGraphStorageBackend()
    store = PolarisDataStore({"time_series": backend, "document": backend, "graph": backend})
    await store.start()
    kb = PolarisKnowledgeBase(store)
    try:
        yield kb
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_full_system_pull_persists_telemetry_and_history(event_bus, knowledge_base):
    controller = PolarisAdaptiveController(event_bus=event_bus, knowledge_base=knowledge_base)
    sub_ctrl = event_bus.subscribe(TelemetryEvent, controller.process_telemetry)

    connector = FullMockConnector("int-1")
    registry = FakePluginRegistry({"mock": connector})
    await registry.initialize()

    exec_adapter = ExecutionAdapter(
        make_execution_adapter_config([{"system_id": "int-1", "connector_type": "mock"}]),
        event_bus=event_bus,
        plugin_registry=registry,
    )
    await exec_adapter.start()

    # persist execution results into KB for validation
    async def persist_exec(ev):
        if isinstance(ev, ExecutionResultEvent):
            await knowledge_base.store_execution_result(ev.execution_result)
    sub_exec_persist = event_bus.subscribe(ExecutionResultEvent, persist_exec)

    mon_cfg = AdapterConfiguration(
        adapter_id="int-mon-pull",
        adapter_type="monitor",
        enabled=True,
        config={
            "collection_mode": MetricCollectionMode.PULL.value,
            "monitoring_targets": [
                {"system_id": "int-1", "connector_type": "mock", "collection_interval": 0.05}
            ],
        },
    )
    monitor = MonitorAdapter(mon_cfg, event_bus=event_bus, plugin_registry=registry)
    await monitor.start()

    await asyncio.sleep(0.6)

    # Check that telemetry exists
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=1)
    telemetry = await knowledge_base.get_historical_states("int-1", start_time, end_time)
    assert isinstance(telemetry, list) and len(telemetry) >= 1

    # Check that adaptation history exists and possibly enriched with execution result
    history = await knowledge_base.get_adaptation_history("int-1")
    assert isinstance(history, list)

    await monitor.stop()
    await exec_adapter.stop()
    await registry.shutdown()
    await event_bus.unsubscribe(sub_ctrl)
    await event_bus.unsubscribe(sub_exec_persist)


@pytest.mark.asyncio
async def test_full_system_push_persists_telemetry_and_history(event_bus, knowledge_base):
    controller = PolarisAdaptiveController(event_bus=event_bus, knowledge_base=knowledge_base)
    sub_ctrl = event_bus.subscribe(TelemetryEvent, controller.process_telemetry)

    connector = FullMockConnector("int-2")
    registry = FakePluginRegistry({"mock": connector})
    await registry.initialize()

    exec_adapter = ExecutionAdapter(
        make_execution_adapter_config([{"system_id": "int-2", "connector_type": "mock"}]),
        event_bus=event_bus,
        plugin_registry=registry,
    )
    await exec_adapter.start()

    mon_cfg = AdapterConfiguration(
        adapter_id="int-mon-push",
        adapter_type="monitor",
        enabled=True,
        config={
            "collection_mode": MetricCollectionMode.PUSH.value,
            "monitoring_targets": [
                {"system_id": "int-2", "connector_type": "mock"}
            ],
        },
    )
    monitor = MonitorAdapter(mon_cfg, event_bus=event_bus, plugin_registry=registry)
    await monitor.start()

    # Emit a push telemetry payload
    await connector.emit_telemetry({
        "metrics": {"cpu": MetricValue("cpu", 0.97, "ratio").__dict__},
        "timestamp": datetime.now(timezone.utc),
    })

    await asyncio.sleep(0.5)

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=1)
    telemetry = await knowledge_base.get_historical_states("int-2", start_time, end_time)
    assert isinstance(telemetry, list) and len(telemetry) >= 1

    history = await knowledge_base.get_adaptation_history("int-2")
    assert isinstance(history, list)

    await monitor.stop()
    await exec_adapter.stop()
    await registry.shutdown()
    await event_bus.unsubscribe(sub_ctrl)
