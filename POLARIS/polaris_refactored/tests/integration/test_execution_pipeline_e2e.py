import asyncio
from datetime import datetime, timezone
import pytest

from polaris_refactored.src.adapters.base_adapter import AdapterConfiguration
from polaris_refactored.src.adapters.execution_adapter.execution_adapter import ExecutionAdapter
from polaris_refactored.src.domain.interfaces import ManagedSystemConnector
from polaris_refactored.src.domain.models import (
    AdaptationAction,
    ExecutionResult,
    ExecutionStatus,
    SystemState,
    MetricValue,
    HealthStatus,
)
from polaris_refactored.src.framework.events import PolarisEventBus, ExecutionResultEvent
from polaris_refactored.src.framework.plugin_management.plugin_registry import PolarisPluginRegistry


class FakeConnector(ManagedSystemConnector):
    def __init__(self, system_id: str, supported_actions=None, behavior=None):
        self._id = system_id
        self._supported = supported_actions or ["scale", "restart"]
        # behavior hooks: dict for controlling failures/timeouts
        self.behavior = behavior or {}
        self._state_counter = 0

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> bool:
        return True

    async def get_system_id(self) -> str:
        return self._id

    async def collect_metrics(self):  # not used
        return {}

    async def get_system_state(self) -> SystemState:
        # Return changing state to simulate pre/post verification
        self._state_counter += 1
        return SystemState(
            system_id=self._id,
            timestamp=datetime.now(timezone.utc),
            metrics={"cpu": MetricValue("cpu", 0.5)},
            health_status=HealthStatus.HEALTHY if self._state_counter % 2 == 1 else HealthStatus.WARNING,
        )

    async def execute_action(self, action: AdaptationAction) -> ExecutionResult:
        if self.behavior.get("raise_execute"):
            raise RuntimeError("boom")
        if self.behavior.get("sleep_execute"):
            # sleep longer than any timeout to trigger timeout
            await asyncio.sleep(self.behavior.get("sleep_execute"))
        return ExecutionResult(action_id=action.action_id, status=ExecutionStatus.SUCCESS, result_data={"ok": True})

    async def validate_action(self, action: AdaptationAction) -> bool:
        if self.behavior.get("invalidate"):
            return False
        return True

    async def get_supported_actions(self):
        return list(self._supported)


class FakePluginRegistry(PolarisPluginRegistry):
    def __init__(self, connectors):
        super().__init__()
        self._fake_connectors = connectors

    async def initialize(self, *args, **kwargs):
        return None

    def load_managed_system_connector(self, system_id: str):
        return self._fake_connectors.get(system_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario,behavior,expected_status,action_timeout", [
    ("success", {}, ExecutionStatus.SUCCESS, None),
    ("validation_fail", {"invalidate": True}, ExecutionStatus.FAILED, None),
    ("timeout", {"sleep_execute": 0.05}, ExecutionStatus.TIMEOUT, 0.01),
    ("execution_error", {"raise_execute": True}, ExecutionStatus.FAILED, None),
])
async def test_execution_pipeline_end_to_end(scenario, behavior, expected_status, action_timeout):
    # Event bus to capture result events
    bus = PolarisEventBus(worker_count=1)
    await bus.start()
    received = []

    async def on_exec(evt: ExecutionResultEvent):
        received.append(evt)

    sub_id = bus.subscribe(type(ExecutionResultEvent(ExecutionResult(action_id="x", status=ExecutionStatus.SUCCESS, result_data={}))), on_exec)

    # Fake registry/connector
    connector = FakeConnector("svc-1", behavior=behavior)
    registry = FakePluginRegistry({"svc-1": connector})

    cfg = AdapterConfiguration(
        adapter_id="exec-1",
        adapter_type="execution",
        config={
            "managed_systems": [
                {"system_id": "svc-1", "connector_type": "svc-1", "config": {}}
            ],
            "pipeline_stages": [
                {"type": "validation"},
                {"type": "pre_condition"},
                {"type": "action_execution"},
                {"type": "post_verification"},
            ],
        },
    )

    adapter = ExecutionAdapter(configuration=cfg, event_bus=bus, plugin_registry=registry)
    await adapter.start()

    action = AdaptationAction(action_id="a1", action_type="scale", target_system="svc-1", parameters={}, timeout_seconds=action_timeout)
    result = await adapter.execute_action(action)

    assert result.status == expected_status

    # Allow event bus to process published result event
    await asyncio.sleep(0.05)
    await bus.stop()
    await adapter.stop()
