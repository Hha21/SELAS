"""
E2E tests focusing on execution pipeline edge cases.
"""

import asyncio
import uuid
from typing import List

import pytest

from polaris_refactored.src.framework.events import PolarisEventBus, AdaptationEvent, ExecutionResultEvent
from polaris_refactored.src.adapters.execution_adapter.execution_adapter import ExecutionAdapter
from polaris_refactored.src.adapters.base_adapter import AdapterConfiguration
from polaris_refactored.src.domain.models import AdaptationAction, ExecutionStatus

import sys 
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent ))

from helpers import MockConnector, FakePluginRegistry, make_execution_adapter_config


@pytest.fixture
async def event_bus():
    bus = PolarisEventBus(worker_count=1)
    await bus.start()
    try:
        yield bus
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_validation_stage_failure_produces_failed_result(event_bus):
    mc = MockConnector("sys-X")
    mc.validate_ok = False
    registry = FakePluginRegistry({"mockX": mc})
    await registry.initialize()

    exec_cfg = make_execution_adapter_config([
        {"system_id": "sys-X", "connector_type": "mockX"}
    ])
    adapter = ExecutionAdapter(exec_cfg, event_bus=event_bus, plugin_registry=registry)
    await adapter.start()

    received: List[ExecutionResultEvent] = []
    async def on_exec(ev):
        if isinstance(ev, ExecutionResultEvent):
            received.append(ev)
    sub_exec = event_bus.subscribe(ExecutionResultEvent, on_exec)

    action = AdaptationAction(str(uuid.uuid4()), "scale_out", "sys-X", {})
    await event_bus.publish(AdaptationEvent(system_id="sys-X", reason="test", suggested_actions=[action]))
    await asyncio.sleep(0.2)

    assert received and received[0].execution_result.status == ExecutionStatus.FAILED

    await event_bus.unsubscribe(sub_exec)
    await adapter.stop()
    await registry.shutdown()


@pytest.mark.asyncio
async def test_precondition_failure_produces_failed_result(event_bus):
    mc = MockConnector("sys-Y")
    # Force get_system_state to raise in pre-condition
    async def raise_state():
        raise RuntimeError("pre-state error")
    mc.get_system_state = raise_state  # type: ignore[assignment]

    registry = FakePluginRegistry({"mockY": mc})
    await registry.initialize()

    exec_cfg = make_execution_adapter_config([
        {"system_id": "sys-Y", "connector_type": "mockY"}
    ])
    adapter = ExecutionAdapter(exec_cfg, event_bus=event_bus, plugin_registry=registry)
    await adapter.start()

    received: List[ExecutionResultEvent] = []
    async def on_exec(ev):
        if isinstance(ev, ExecutionResultEvent):
            received.append(ev)
    sub_exec = event_bus.subscribe(ExecutionResultEvent, on_exec)

    action = AdaptationAction(str(uuid.uuid4()), "scale_out", "sys-Y", {})
    await event_bus.publish(AdaptationEvent(system_id="sys-Y", reason="test", suggested_actions=[action]))
    await asyncio.sleep(0.2)

    assert received and received[0].execution_result.status == ExecutionStatus.FAILED

    await event_bus.unsubscribe(sub_exec)
    await adapter.stop()
    await registry.shutdown()


@pytest.mark.asyncio
async def test_connector_execute_exception_maps_to_failed(event_bus):
    mc = MockConnector("sys-Z")
    mc.fail_execute = True
    registry = FakePluginRegistry({"mockZ": mc})
    await registry.initialize()

    exec_cfg = make_execution_adapter_config([
        {"system_id": "sys-Z", "connector_type": "mockZ"}
    ])
    adapter = ExecutionAdapter(exec_cfg, event_bus=event_bus, plugin_registry=registry)
    await adapter.start()

    received: List[ExecutionResultEvent] = []
    async def on_exec(ev):
        if isinstance(ev, ExecutionResultEvent):
            received.append(ev)
    sub_exec = event_bus.subscribe(ExecutionResultEvent, on_exec)

    action = AdaptationAction(str(uuid.uuid4()), "scale_out", "sys-Z", {})
    await event_bus.publish(AdaptationEvent(system_id="sys-Z", reason="test", suggested_actions=[action]))
    await asyncio.sleep(0.3)

    assert received and received[0].execution_result.status == ExecutionStatus.FAILED

    await event_bus.unsubscribe(sub_exec)
    await adapter.stop()
    await registry.shutdown()
