import asyncio
import pytest

from polaris_refactored.src.adapters.base_adapter import AdapterConfiguration
from polaris_refactored.src.adapters.execution_adapter import ExecutionAdapter
from polaris_refactored.src.domain.models import AdaptationAction, ExecutionStatus, ExecutionResult, SystemState, MetricValue, HealthStatus
from polaris_refactored.src.framework.events import PolarisEventBus, ExecutionResultEvent

# Minimal fake plugin registry compatible with ManagedSystemConnectorFactory
class FakePluginRegistry:
    def __init__(self, connectors):
        # connectors: dict system_id -> connector instance
        self._connectors = connectors

    # Factory expects this method
    def load_managed_system_connector(self, system_id: str):
        return self._connectors.get(system_id)

    # Some factory helper methods may reference these in future; keep stubs
    def get_plugin_descriptors(self):
        return {}

    def is_plugin_loaded(self, system_id: str) -> bool:
        return system_id in self._connectors


# Minimal connector implementing the interface
from polaris_refactored.src.domain.interfaces import ManagedSystemConnector
from datetime import datetime, timezone


class BasicConnector(ManagedSystemConnector):
    def __init__(self, system_id="system-A", supported=None, delay_execution=0.0, fail_execute=False, fail_post_verify=False):
        self._system_id = system_id
        self._supported = supported or ["TEST_ACTION"]
        self._delay = delay_execution
        self._fail_execute = fail_execute
        self._fail_post_verify = fail_post_verify
        self._get_state_calls = 0
        self._state = SystemState(
            system_id=system_id,
            timestamp=datetime.now(timezone.utc),
            metrics={"dummy": MetricValue(name="dummy", value=1)},
            health_status=HealthStatus.HEALTHY,
        )

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> bool:
        return True

    async def get_system_id(self) -> str:
        return self._system_id

    async def collect_metrics(self):
        return self._state.metrics

    async def get_system_state(self) -> SystemState:
        self._get_state_calls += 1
        if self._fail_post_verify and self._get_state_calls >= 2:
            raise RuntimeError("post verification state fetch failed")
        return self._state

    async def execute_action(self, action: AdaptationAction) -> ExecutionResult:
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        if self._fail_execute:
            raise RuntimeError("execution error")
        return ExecutionResult(
            action_id=action.action_id,
            status=ExecutionStatus.SUCCESS,
            result_data={"ok": True},
        )

    async def validate_action(self, action: AdaptationAction) -> bool:
        return True

    async def get_supported_actions(self):
        return list(self._supported)


@pytest.mark.asyncio
async def test_adapter_config_validation_missing_stages():
    cfg = AdapterConfiguration(
        adapter_id="exec-1",
        adapter_type="execution",
        enabled=True,
        config={
            # missing pipeline_stages
            "managed_systems": [
                {"system_id": "system-A", "connector_type": "system-A", "config": {}},
            ]
        },
    )
    adapter = ExecutionAdapter(configuration=cfg, event_bus=PolarisEventBus(), plugin_registry=FakePluginRegistry({}))
    with pytest.raises(Exception):
        await adapter.start()


@pytest.mark.asyncio
async def test_adapter_connector_resolution_failure():
    cfg = AdapterConfiguration(
        adapter_id="exec-2",
        adapter_type="execution",
        enabled=True,
        config={
            "pipeline_stages": [
                {"type": "validation"},
                {"type": "pre_condition"},
                {"type": "action_execution"},
                {"type": "post_verification"},
            ],
            "managed_systems": [
                # Only system-A is mapped
                {"system_id": "system-A", "connector_type": "system-A", "config": {}},
            ],
            "stage_timeouts": {"action_execution": 1},
        },
    )
    event_bus = PolarisEventBus()
    await event_bus.start()
    adapter = ExecutionAdapter(configuration=cfg, event_bus=event_bus, plugin_registry=FakePluginRegistry({}))
    await adapter.start()

    action = AdaptationAction(action_id="x1", action_type="TEST_ACTION", target_system="system-B", parameters={})

    with pytest.raises(RuntimeError):
        await adapter.execute_action(action)

    await adapter.stop()
    await event_bus.stop()


@pytest.mark.asyncio
async def test_adapter_execute_action_success_and_event_publishing():
    connector = BasicConnector(system_id="system-A")
    registry = FakePluginRegistry({"system-A": connector})
    cfg = AdapterConfiguration(
        adapter_id="exec-3",
        adapter_type="execution",
        enabled=True,
        config={
            "pipeline_stages": [
                {"type": "validation"},
                {"type": "pre_condition"},
                {"type": "action_execution"},
                {"type": "post_verification"},
            ],
            "managed_systems": [
                {"system_id": "system-A", "connector_type": "system-A", "config": {}},
            ],
            "stage_timeouts": {"action_execution": 2},
        },
    )

    event_bus = PolarisEventBus()
    await event_bus.start()

    # Capture published execution events
    received = []

    async def handler(event: ExecutionResultEvent):
        received.append(event)

    sub_id = event_bus.subscribe(ExecutionResultEvent, handler)

    adapter = ExecutionAdapter(configuration=cfg, event_bus=event_bus, plugin_registry=registry)
    await adapter.start()

    action = AdaptationAction(action_id="x2", action_type="TEST_ACTION", target_system="system-A", parameters={})
    result = await adapter.execute_action(action)

    # Give event bus time to process
    await asyncio.sleep(0.1)

    assert result.status == ExecutionStatus.SUCCESS
    assert received, "Expected an ExecutionResultEvent to be published"

    await adapter.stop()
    await event_bus.stop()


@pytest.mark.asyncio
async def test_adapter_execute_action_timeout():
    # Connector sleeps longer than timeout
    connector = BasicConnector(system_id="system-A", delay_execution=1.0)
    registry = FakePluginRegistry({"system-A": connector})
    cfg = AdapterConfiguration(
        adapter_id="exec-4",
        adapter_type="execution",
        enabled=True,
        config={
            "pipeline_stages": [
                {"type": "validation"},
                {"type": "pre_condition"},
                {"type": "action_execution"},
                {"type": "post_verification"},
            ],
            "managed_systems": [
                {"system_id": "system-A", "connector_type": "system-A", "config": {}},
            ],
            "stage_timeouts": {"action_execution": 0},
        },
    )

    event_bus = PolarisEventBus()
    await event_bus.start()

    adapter = ExecutionAdapter(configuration=cfg, event_bus=event_bus, plugin_registry=registry)
    await adapter.start()

    action = AdaptationAction(action_id="x3", action_type="TEST_ACTION", target_system="system-A", parameters={})
    result = await adapter.execute_action(action)

    assert result.status in (ExecutionStatus.TIMEOUT, ExecutionStatus.FAILED)

    await adapter.stop()
    await event_bus.stop()


@pytest.mark.asyncio
async def test_adapter_unsupported_action_validation_failure():
    # Connector supports only OTHER_ACTION
    connector = BasicConnector(system_id="system-A", supported=["OTHER_ACTION"]) 
    registry = FakePluginRegistry({"system-A": connector})
    cfg = AdapterConfiguration(
        adapter_id="exec-5",
        adapter_type="execution",
        enabled=True,
        config={
            "pipeline_stages": [
                {"type": "validation"},
                {"type": "pre_condition"},
                {"type": "action_execution"},
                {"type": "post_verification"},
            ],
            "managed_systems": [
                {"system_id": "system-A", "connector_type": "system-A", "config": {}},
            ],
            "stage_timeouts": {"action_execution": 1},
        },
    )

    event_bus = PolarisEventBus()
    await event_bus.start()

    adapter = ExecutionAdapter(configuration=cfg, event_bus=event_bus, plugin_registry=registry)
    await adapter.start()

    action = AdaptationAction(action_id="x4", action_type="TEST_ACTION", target_system="system-A", parameters={})
    result = await adapter.execute_action(action)

    assert result.status == ExecutionStatus.FAILED
    assert result.error_message is not None

    await adapter.stop()
    await event_bus.stop()


@pytest.mark.asyncio
async def test_adapter_post_verification_degrades_to_partial():
    # First get_system_state works (pre), second (post) fails triggering PARTIAL
    connector = BasicConnector(system_id="system-A", fail_post_verify=True)
    registry = FakePluginRegistry({"system-A": connector})
    cfg = AdapterConfiguration(
        adapter_id="exec-6",
        adapter_type="execution",
        enabled=True,
        config={
            "pipeline_stages": [
                {"type": "validation"},
                {"type": "pre_condition"},
                {"type": "action_execution"},
                {"type": "post_verification"},
            ],
            "managed_systems": [
                {"system_id": "system-A", "connector_type": "system-A", "config": {}},
            ],
            "stage_timeouts": {"action_execution": 1},
        },
    )

    event_bus = PolarisEventBus()
    await event_bus.start()

    adapter = ExecutionAdapter(configuration=cfg, event_bus=event_bus, plugin_registry=registry)
    await adapter.start()

    action = AdaptationAction(action_id="x5", action_type="TEST_ACTION", target_system="system-A", parameters={})
    result = await adapter.execute_action(action)

    assert result.status in (ExecutionStatus.SUCCESS, ExecutionStatus.PARTIAL)
    # If post verification failed, status should be PARTIAL
    if result.error_message:
        assert result.status == ExecutionStatus.PARTIAL

    await adapter.stop()
    await event_bus.stop()


@pytest.mark.asyncio
async def test_adapter_lifecycle_start_stop_idempotent():
    connector = BasicConnector(system_id="system-A")
    registry = FakePluginRegistry({"system-A": connector})
    cfg = AdapterConfiguration(
        adapter_id="exec-7",
        adapter_type="execution",
        enabled=True,
        config={
            "pipeline_stages": [
                {"type": "validation"},
                {"type": "pre_condition"},
                {"type": "action_execution"},
                {"type": "post_verification"},
            ],
            "managed_systems": [
                {"system_id": "system-A", "connector_type": "system-A", "config": {}},
            ],
        },
    )

    event_bus = PolarisEventBus()
    await event_bus.start()

    adapter = ExecutionAdapter(configuration=cfg, event_bus=event_bus, plugin_registry=registry)
    await adapter.start()
    # Start again should not raise (base adapter handles state)
    await adapter.start()

    await adapter.stop()
    # Stop again should not raise
    await adapter.stop()

    await event_bus.stop()
