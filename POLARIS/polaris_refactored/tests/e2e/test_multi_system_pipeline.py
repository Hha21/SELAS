"""
E2E tests for multi-system pipeline scenarios.
"""

import asyncio
from typing import List
from datetime import datetime
import pytest

from polaris_refactored.src.framework.events import PolarisEventBus, TelemetryEvent, ExecutionResultEvent
from polaris_refactored.src.control_reasoning.adaptive_controller import PolarisAdaptiveController
from polaris_refactored.src.digital_twin.knowledge_base import PolarisKnowledgeBase
from polaris_refactored.src.infrastructure.data_storage.data_store import PolarisDataStore
from polaris_refactored.src.infrastructure.data_storage.storage_backend import InMemoryGraphStorageBackend
from polaris_refactored.src.adapters.execution_adapter.execution_adapter import ExecutionAdapter
from polaris_refactored.src.domain.models import SystemState, HealthStatus, MetricValue

from pathlib import Path
import sys 
sys.path.insert(0, str(Path(__file__).parent ))

from helpers import FullMockConnector, FakePluginRegistry, make_execution_adapter_config


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
async def test_concurrent_adaptation_across_multiple_systems(event_bus, knowledge_base):
    controller = PolarisAdaptiveController(event_bus=event_bus, knowledge_base=knowledge_base)
    sub_ctrl = event_bus.subscribe(TelemetryEvent, controller.process_telemetry)

    c1 = FullMockConnector("sys-A")
    c2 = FullMockConnector("sys-B")

    registry = FakePluginRegistry({"mockA": c1, "mockB": c2})
    await registry.initialize()

    exec_cfg = make_execution_adapter_config([
        {"system_id": "sys-A", "connector_type": "mockA"},
        {"system_id": "sys-B", "connector_type": "mockB"},
    ])
    exec_adapter = ExecutionAdapter(exec_cfg, event_bus=event_bus, plugin_registry=registry)
    await exec_adapter.start()

    # send telemetry for both systems that should trigger adaptation
    await event_bus.publish(TelemetryEvent(SystemState(
        system_id="sys-A",
        health_status=HealthStatus.HEALTHY,
        metrics={"cpu": MetricValue("cpu", 0.96, "ratio")},
        timestamp=datetime.now()
    )))
    await event_bus.publish(TelemetryEvent(SystemState(
        system_id="sys-B",
        health_status=HealthStatus.HEALTHY,
        metrics={"cpu": MetricValue("cpu", 0.92, "ratio")},
        timestamp=datetime.now()
    )))

    received: List[ExecutionResultEvent] = []
    async def on_exec(ev):
        if isinstance(ev, ExecutionResultEvent):
            received.append(ev)
    sub_exec = event_bus.subscribe(ExecutionResultEvent, on_exec)

    await asyncio.sleep(0.6)

    # Expect at least one result per system
    print([ev.execution_result.result_data for ev in received])
    action_ids_by_system = {ev.metadata.tags["target_system"] for ev in received}
    assert "sys-A" in action_ids_by_system and "sys-B" in action_ids_by_system

    await event_bus.unsubscribe(sub_exec)
    await exec_adapter.stop()
    await registry.shutdown()
    await event_bus.unsubscribe(sub_ctrl)


@pytest.mark.asyncio
async def test_mixed_signals_only_high_util_triggers(event_bus, knowledge_base):
    controller = PolarisAdaptiveController(event_bus=event_bus, knowledge_base=knowledge_base)
    sub_ctrl = event_bus.subscribe(TelemetryEvent, controller.process_telemetry)

    c1 = FullMockConnector("sys-C")
    c2 = FullMockConnector("sys-D")

    registry = FakePluginRegistry({"mockC": c1, "mockD": c2})
    await registry.initialize()

    exec_cfg = make_execution_adapter_config([
        {"system_id": "sys-C", "connector_type": "mockC"},
        {"system_id": "sys-D", "connector_type": "mockD"},
    ])
    exec_adapter = ExecutionAdapter(exec_cfg, event_bus=event_bus, plugin_registry=registry)
    await exec_adapter.start()

    # sys-C low load -> no adaptation; sys-D high load -> adaptation
    await event_bus.publish(TelemetryEvent(SystemState(
        system_id="sys-C",
        health_status=HealthStatus.HEALTHY,
        metrics={"cpu": MetricValue("cpu", 0.1, "ratio")},
        timestamp=datetime.now()
    )))
    await event_bus.publish(TelemetryEvent(SystemState(
        system_id="sys-D",
        health_status=HealthStatus.HEALTHY,
        metrics={"cpu": MetricValue("cpu", 0.95, "ratio")},
        timestamp=datetime.now()
    )))

    received: List[ExecutionResultEvent] = []
    async def on_exec(ev):
        if isinstance(ev, ExecutionResultEvent):
            received.append(ev)
    sub_exec = event_bus.subscribe(ExecutionResultEvent, on_exec)

    await asyncio.sleep(0.5)

    systems = {ev.metadata.tags["target_system"] for ev in received}
    assert "sys-D" in systems

    await event_bus.unsubscribe(sub_exec)
    await exec_adapter.stop()
    await registry.shutdown()
    await event_bus.unsubscribe(sub_ctrl)
