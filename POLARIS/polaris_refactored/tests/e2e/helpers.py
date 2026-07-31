"""
Shared test utilities for POLARIS E2E/Integration tests.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from polaris_refactored.src.domain.interfaces import ManagedSystemConnector
from polaris_refactored.src.domain.models import (
    SystemState,
    HealthStatus,
    MetricValue,
    AdaptationAction,
    ExecutionResult,
    ExecutionStatus,
)
from polaris_refactored.src.framework.plugin_management import PolarisPluginRegistry
from polaris_refactored.src.adapters.base_adapter import AdapterConfiguration


class MockConnector(ManagedSystemConnector):
    """A simple mock connector for tests with configurable behavior."""

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
        return ["scale_out", "tune_qos", "restart", "noop"]


class FullMockConnector(MockConnector):
    """Extends MockConnector with PUSH telemetry support."""

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


class FakePluginRegistry(PolarisPluginRegistry):
    """Minimal stub over PolarisPluginRegistry to inject connectors by type."""

    def __init__(self, mapping: Dict[str, ManagedSystemConnector]):
        super().__init__()
        self._mapping = mapping

    def load_managed_system_connector(self, system_id: str) -> Optional[ManagedSystemConnector]:  # type: ignore[override]
        return self._mapping.get(system_id)


def make_execution_adapter_config(managed_systems: List[Dict[str, str]], stage_timeouts: Optional[Dict[str, float]] = None) -> AdapterConfiguration:
    cfg = {
        "pipeline_stages": [
            {"type": "validation"},
            {"type": "pre_condition"},
            {"type": "action_execution"},
            {"type": "post_verification"},
        ],
        "managed_systems": managed_systems,
    }
    if stage_timeouts:
        cfg["stage_timeouts"] = stage_timeouts
    return AdapterConfiguration(
        adapter_id=f"exec-{uuid.uuid4()}",
        adapter_type="execution",
        enabled=True,
        config=cfg,
    )
