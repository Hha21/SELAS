"""
End-to-end tests for POLARIS core pipeline

Covers Monitor/Telemetry -> Adaptive Controller -> Adaptation Event -> Execution Adapter
with an in-memory event bus and a fake plugin registry + mock connector.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import pytest

from polaris_refactored.src.framework.events import (
    PolarisEventBus,
    TelemetryEvent,
    EventMetadata,
    AdaptationEvent,
    ExecutionResultEvent,
)
from polaris_refactored.src.adapters.base_adapter import AdapterConfiguration
from polaris_refactored.src.adapters.execution_adapter.execution_adapter import ExecutionAdapter
from polaris_refactored.src.adapters.monitor_adapter.monitor_adapter import MonitorAdapter
from polaris_refactored.src.adapters.monitor_adapter.monitor_types import MonitoringTarget, MetricCollectionMode
from polaris_refactored.src.control_reasoning.adaptive_controller import PolarisAdaptiveController
from polaris_refactored.src.domain.models import (
    SystemState,
    HealthStatus,
    MetricValue,
    AdaptationAction,
    ExecutionResult,
    ExecutionStatus,
)
from polaris_refactored.src.domain.interfaces import ManagedSystemConnector
from polaris_refactored.src.framework.plugin_management import PolarisPluginRegistry, ManagedSystemConnectorFactory
from polaris_refactored.src.infrastructure.data_storage.data_store import PolarisDataStore
from polaris_refactored.src.infrastructure.data_storage.storage_backend import InMemoryGraphStorageBackend
from polaris_refactored.src.digital_twin.knowledge_base import PolarisKnowledgeBase
from polaris_refactored.src.digital_twin.telemetry_subscriber import subscribe_telemetry_persistence


# ---------- Test Utilities ----------

class MockConnector(ManagedSystemConnector):
    """A simple mock connector for E2E tests.

    Supports actions: "scale_out", "tune_qos".
    Can be configured to delay or fail execution or post-state queries.
    """

    def __init__(self, system_id: str = "system-A"):
        self.system_id = system_id
        self.connected = False
        self.validate_ok = True
        self.fail_execute = False
        self.exec_delay = 0.0
        self.fail_post_state = False
        self.metrics_template: Dict[str, MetricValue] = {
            "cpu": MetricValue("cpu", 0.95, "ratio"),
            "latency": MetricValue("latency", 0.2, "ratio"),
        }

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def disconnect(self) -> bool:
        self.connected = False
        return True

    async def get_system_id(self) -> str:
        return self.system_id

    async def collect_metrics(self) -> Dict[str, MetricValue]:
        return dict(self.metrics_template)

    async def get_system_state(self) -> SystemState:
        if self.fail_post_state:
            raise RuntimeError("post-state fetch failed")
        return SystemState(
            system_id=self.system_id,
            health_status=HealthStatus.HEALTHY,
            metrics=dict(self.metrics_template),
            timestamp=datetime.now(timezone.utc),
        )

    async def execute_action(self, action: AdaptationAction) -> ExecutionResult:
        if self.exec_delay > 0:
            await asyncio.sleep(self.exec_delay)
        if self.fail_execute:
            raise RuntimeError("execution error")
        return ExecutionResult(
            action_id=action.action_id,
            status=ExecutionStatus.SUCCESS,
            result_data={"ok": True, "action_type": action.action_type},
        )

    async def validate_action(self, action: AdaptationAction) -> bool:
        return self.validate_ok

    async def get_supported_actions(self) -> List[str]:
        return ["scale_out", "tune_qos"]


class FakePluginRegistry(PolarisPluginRegistry):
    """Minimal stub over PolarisPluginRegistry to inject connectors by type."""

    def __init__(self, mapping: Dict[str, ManagedSystemConnector]):
        super().__init__()
        self._mapping = mapping

    def load_managed_system_connector(self, system_id: str) -> Optional[ManagedSystemConnector]:  # type: ignore[override]
        # Return a connector instance; for simplicity we return the same instance
        return self._mapping.get(system_id)


class FullMockConnector(MockConnector):
    """Extends MockConnector with PUSH telemetry support.

    Implements subscribe_telemetry/unsubscribe and an emit_telemetry() helper.
    """

    def __init__(self, system_id: str = "system-A"):
        super().__init__(system_id=system_id)
        self._push_handler = None
        self._token_counter = 0

    # push subscription API expected by MonitorAdapter
    def subscribe_telemetry(self, handler):
        self._token_counter += 1
        self._push_handler = handler
        return f"tok-{self._token_counter}"

    def unsubscribe(self, token):
        # simple noop for tests
        self._push_handler = None

    async def emit_telemetry(self, payload):
        if self._push_handler:
            await self._push_handler(payload)


# ---------- Pytest fixtures ----------

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
    # Use in-memory graph storage for all backend roles for tests
    backend = InMemoryGraphStorageBackend()
    store = PolarisDataStore(storage_backends={
        "time_series": backend,
        "document": backend,
        "graph": backend,
    })
    await store.start()
    kb = PolarisKnowledgeBase(store)
    try:
        yield kb
    finally:
        await store.stop()


@pytest.fixture
async def controller(event_bus, knowledge_base):
    ctrl = PolarisAdaptiveController(event_bus=event_bus, knowledge_base=knowledge_base)

    # Wire controller to telemetry events
    sub_id = event_bus.subscribe(TelemetryEvent, ctrl.process_telemetry)
    # Also persist telemetry into KB
    kb_sub_id = await subscribe_telemetry_persistence(event_bus, knowledge_base)

    try:
        yield ctrl
    finally:
        await event_bus.unsubscribe(sub_id)
        await event_bus.unsubscribe(kb_sub_id)


def _execution_adapter_config() -> AdapterConfiguration:
    cfg = {
        "pipeline_stages": [
            {"type": "validation"},
            {"type": "pre_condition"},
            {"type": "action_execution"},
            {"type": "post_verification"},
        ],
        "stage_timeouts": {"action_execution": 2},
        "managed_systems": [
            {
                "system_id": "system-A",
                "connector_type": "mock_connector",
                "config": {},
            }
        ],
    }
    return AdapterConfiguration(
        adapter_id="exec-1",
        adapter_type="execution",
        enabled=True,
        config=cfg,
    )


@pytest.fixture
async def execution_adapter(event_bus):
    # Prepare fake plugin registry and factory
    connector = MockConnector(system_id="system-A")
    registry = FakePluginRegistry({"mock_connector": connector})
    await registry.initialize()  # no-op discovery

    adapter = ExecutionAdapter(
        configuration=_execution_adapter_config(),
        event_bus=event_bus,
        plugin_registry=registry,
    )
    await adapter.start()
    try:
        yield adapter
    finally:
        await adapter.stop()
        await registry.shutdown()


# ---------- Tests ----------

@pytest.mark.asyncio
async def test_end_to_end_success_path(event_bus, controller, execution_adapter, knowledge_base):
    """Healthy telemetry with high CPU triggers adaptation and successful execution."""
    received_exec_events: List[ExecutionResultEvent] = []

    async def on_exec(ev):
        if isinstance(ev, ExecutionResultEvent):
            received_exec_events.append(ev)

    sub_id = event_bus.subscribe(ExecutionResultEvent, on_exec)

    # Publish telemetry with high CPU to trigger ReactiveControlStrategy -> scale_out
    telemetry = TelemetryEvent(
        system_state=SystemState(
            system_id="system-A",
            health_status=HealthStatus.HEALTHY,
            metrics={"cpu": MetricValue("cpu", 0.95, "ratio")},
            timestamp=datetime.now(timezone.utc),
        ),
        metadata=EventMetadata(source="test")
    )
    await event_bus.publish(telemetry)

    # Allow processing chain to complete
    await asyncio.sleep(0.4)

    assert len(received_exec_events) >= 1
    ev = received_exec_events[0]
    assert ev.execution_result.status == ExecutionStatus.SUCCESS

    await event_bus.unsubscribe(sub_id)


@pytest.mark.asyncio
async def test_execution_timeout(event_bus):
    """ActionExecutionStage timeout yields TIMEOUT result and event.

    We publish an AdaptationEvent with an action-level timeout and rely on the
    stage internal timeout handling (no pipeline-level timeout for action stage).
    """
    # Setup execution adapter with slow connector
    connector = MockConnector(system_id="system-A")
    connector.exec_delay = 0.3
    registry = FakePluginRegistry({"mock_connector": connector})
    await registry.initialize()

    cfg = _execution_adapter_config()
    # Remove pipeline-level timeout for action_execution so inner stage handles timeout
    cfg.config["stage_timeouts"].pop("action_execution", None)
    adapter = ExecutionAdapter(configuration=cfg, event_bus=event_bus, plugin_registry=registry)
    await adapter.start()

    received: List[ExecutionResultEvent] = []
    async def on_exec(ev):
        if isinstance(ev, ExecutionResultEvent):
            received.append(ev)

    sub_id = event_bus.subscribe(ExecutionResultEvent, on_exec)

    # Directly publish an adaptation event with a short action timeout
    action = AdaptationAction(
        action_id=str(uuid.uuid4()),
        action_type="scale_out",
        target_system="system-A",
        parameters={"scale_factor": 2},
        timeout_seconds=0.05,
    )
    adaptation = AdaptationEvent(system_id="system-A", reason="test", suggested_actions=[action])

    await event_bus.publish(adaptation)
    await asyncio.sleep(0.5)

    assert received, "Expected an execution result event"
    assert received[0].execution_result.status == ExecutionStatus.TIMEOUT

    await event_bus.unsubscribe(sub_id)
    await adapter.stop()
    await registry.shutdown()


@pytest.mark.asyncio
async def test_post_verification_degrades_on_state_fetch_error(event_bus, knowledge_base):
    """If post-state fetch fails, ExecutionResult should degrade to PARTIAL."""
    connector = MockConnector(system_id="system-A")
    # Make first state call succeed (pre-condition), second (post) fail
    call_count = {"n": 0}
    async def wrapped_get_state():
        call_count["n"] += 1
        if call_count["n"] == 1:
            return await MockConnector.get_system_state(connector)
        raise RuntimeError("post-state fetch failed")
    connector.get_system_state = wrapped_get_state  # type: ignore[assignment]
    registry = FakePluginRegistry({"mock_connector": connector})
    await registry.initialize()

    adapter = ExecutionAdapter(configuration=_execution_adapter_config(), event_bus=event_bus, plugin_registry=registry)
    await adapter.start()

    # Directly craft an adaptation event to go straight to execution
    action = AdaptationAction(
        action_id=str(uuid.uuid4()),
        action_type="scale_out",
        target_system="system-A",
        parameters={"scale_factor": 2},
    )
    adaptation = AdaptationEvent(system_id="system-A", reason="test", suggested_actions=[action])

    received: List[ExecutionResultEvent] = []
    async def on_exec(ev):
        if isinstance(ev, ExecutionResultEvent):
            received.append(ev)

    sub_id = event_bus.subscribe(ExecutionResultEvent, on_exec)

    await event_bus.publish(adaptation)
    await asyncio.sleep(0.3)

    assert received, "Expected an execution result event"
    assert received[0].execution_result.status == ExecutionStatus.PARTIAL

    await event_bus.unsubscribe(sub_id)
    await adapter.stop()
    await registry.shutdown()


@pytest.mark.asyncio
async def test_healthy_telemetry_no_adaptation(event_bus, controller):
    """Healthy, low metrics should not trigger an AdaptationEvent."""
    received_adapt: List[AdaptationEvent] = []

    async def on_adapt(ev):
        if isinstance(ev, AdaptationEvent):
            received_adapt.append(ev)

    sub_id = event_bus.subscribe(AdaptationEvent, on_adapt)

    telemetry = TelemetryEvent(
        system_state=SystemState(
            system_id="system-A",
            health_status=HealthStatus.HEALTHY,
            metrics={"cpu": MetricValue("cpu", 0.1, "ratio"), "latency": MetricValue("latency", 0.1, "ratio")},
            timestamp=datetime.now(timezone.utc),
        ),
        metadata=EventMetadata(source="test")
    )
    await event_bus.publish(telemetry)
    await asyncio.sleep(0.3)

    # No adaptation event expected
    assert len(received_adapt) == 0

    await event_bus.unsubscribe(sub_id)
