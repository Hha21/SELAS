"""
E2E tests for MonitorAdapter in PULL and PUSH modes.
"""

import asyncio
from datetime import datetime, timezone
from typing import List

import pytest

from polaris_refactored.src.adapters.base_adapter import AdapterConfiguration
from polaris_refactored.src.adapters.monitor_adapter.monitor_adapter import MonitorAdapter
from polaris_refactored.src.adapters.monitor_adapter.monitor_types import MetricCollectionMode
from polaris_refactored.src.adapters.execution_adapter.execution_adapter import ExecutionAdapter
from polaris_refactored.src.framework.events import PolarisEventBus, TelemetryEvent, ExecutionResultEvent
from polaris_refactored.src.digital_twin.knowledge_base import PolarisKnowledgeBase
from polaris_refactored.src.infrastructure.data_storage.data_store import PolarisDataStore
from polaris_refactored.src.infrastructure.data_storage.storage_backend import InMemoryGraphStorageBackend
from polaris_refactored.src.control_reasoning.adaptive_controller import PolarisAdaptiveController

from pathlib import Path
import sys 
sys.path.insert(0, str(Path(__file__).parent ))

from helpers import FullMockConnector, FakePluginRegistry, make_execution_adapter_config
from polaris_refactored.src.domain.models import MetricValue


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
async def test_pull_mode_collects_and_triggers_execution(event_bus, knowledge_base):
    controller = PolarisAdaptiveController(event_bus=event_bus, knowledge_base=knowledge_base)
    sub_ctrl = event_bus.subscribe(TelemetryEvent, controller.process_telemetry)

    connector = FullMockConnector("sys-1")
    registry = FakePluginRegistry({"mock_connector": connector})
    await registry.initialize()

    exec_cfg = make_execution_adapter_config([
        {"system_id": "sys-1", "connector_type": "mock_connector"}
    ])
    exec_adapter = ExecutionAdapter(exec_cfg, event_bus=event_bus, plugin_registry=registry)
    await exec_adapter.start()

    mon_cfg = AdapterConfiguration(
        adapter_id="mon-pull",
        adapter_type="monitor",
        enabled=True,
        config={
            "collection_mode": MetricCollectionMode.PULL.value,
            "monitoring_targets": [
                {"system_id": "sys-1", "connector_type": "mock_connector", "collection_interval": 0.05}
            ],
        },
    )
    monitor = MonitorAdapter(mon_cfg, event_bus=event_bus, plugin_registry=registry)
    await monitor.start()

    received: List[ExecutionResultEvent] = []
    async def on_exec(ev):
        if isinstance(ev, ExecutionResultEvent):
            received.append(ev)
    sub_exec = event_bus.subscribe(ExecutionResultEvent, on_exec)

    await asyncio.sleep(0.5)

    assert len(received) >= 1

    await event_bus.unsubscribe(sub_exec)
    await monitor.stop()
    await exec_adapter.stop()
    await registry.shutdown()
    await event_bus.unsubscribe(sub_ctrl)


@pytest.mark.asyncio
async def test_push_mode_emits_and_triggers_execution(event_bus, knowledge_base):
    controller = PolarisAdaptiveController(event_bus=event_bus, knowledge_base=knowledge_base)
    sub_ctrl = event_bus.subscribe(TelemetryEvent, controller.process_telemetry)

    connector = FullMockConnector("sys-2")
    registry = FakePluginRegistry({"mock_connector": connector})
    await registry.initialize()

    exec_cfg = make_execution_adapter_config([
        {"system_id": "sys-2", "connector_type": "mock_connector"}
    ])
    exec_adapter = ExecutionAdapter(exec_cfg, event_bus=event_bus, plugin_registry=registry)
    await exec_adapter.start()

    mon_cfg = AdapterConfiguration(
        adapter_id="mon-push",
        adapter_type="monitor",
        enabled=True,
        config={
            "collection_mode": MetricCollectionMode.PUSH.value,
            "monitoring_targets": [
                {"system_id": "sys-2", "connector_type": "mock_connector"}
            ],
        },
    )
    monitor = MonitorAdapter(mon_cfg, event_bus=event_bus, plugin_registry=registry)
    await monitor.start()

    # Emit telemetry via connector
    await connector.emit_telemetry({
        "metrics": {"cpu": MetricValue("cpu", 0.95, "ratio").__dict__},
        "timestamp": datetime.now(timezone.utc),
    })

    received: List[ExecutionResultEvent] = []
    async def on_exec(ev):
        if isinstance(ev, ExecutionResultEvent):
            received.append(ev)
    sub_exec = event_bus.subscribe(ExecutionResultEvent, on_exec)

    await asyncio.sleep(0.5)

    assert len(received) >= 1

    await event_bus.unsubscribe(sub_exec)
    await monitor.stop()
    await exec_adapter.stop()
    await registry.shutdown()
    await event_bus.unsubscribe(sub_ctrl)
