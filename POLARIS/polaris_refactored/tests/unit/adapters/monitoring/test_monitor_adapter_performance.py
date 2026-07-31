"""
Performance and Load Testing for Monitor Adapter

Tests for handling high load, backpressure, and performance scenarios.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from polaris_refactored.src.adapters.monitor_adapter.monitor_adapter import MonitorAdapter
from polaris_refactored.src.adapters.monitor_adapter.monitor_types import MonitoringTarget, MetricCollectionMode
from polaris_refactored.src.adapters.base_adapter import AdapterConfiguration
from polaris_refactored.src.framework.events import PolarisEventBus
from polaris_refactored.src.domain.models import MetricValue, SystemState, HealthStatus
from polaris_refactored.src.domain.interfaces import ManagedSystemConnector
from polaris_refactored.src.framework.events import TelemetryEvent as RealTelemetryEvent

class MockFastConnector(ManagedSystemConnector):
    """Fast connector for performance testing."""
    def __init__(self, system_id: str = "test-system"):
        self._system_id = system_id
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.collect_calls = 0
        self.state_calls = 0

    async def connect(self) -> bool:
        self.connect_calls += 1
        return True

    async def disconnect(self) -> bool:
        self.disconnect_calls += 1
        return True

    def get_system_id(self) -> str:
        return self._system_id

    async def collect_metrics(self) -> dict[str, MetricValue]:
        self.collect_calls += 1
        return {
            "cpu_usage": MetricValue("cpu_usage", 50.0, "percent"),
            "memory_usage": MetricValue("memory_usage", 60.0, "percent")
        }

    async def get_system_state(self) -> SystemState:
        self.state_calls += 1
        return SystemState(
            system_id=self._system_id,
            health_status=HealthStatus.HEALTHY,
            metrics={
                "cpu_usage": MetricValue("cpu_usage", 50.0, "percent"),
                "memory_usage": MetricValue("memory_usage", 60.0, "percent")
            }
        )

    def get_supported_actions(self) -> list[str]:
        return []

    async def validate_action(self, action: str, params: dict) -> bool:
        return False

    async def execute_action(self, action: str, params: dict) -> dict:
        raise NotImplementedError("MockFastConnector does not support actions.")


class TestMonitorAdapterPerformance:
    """Performance and load testing for Monitor Adapter."""

    FACTORY_PATH = "polaris_refactored.src.adapters.monitor_adapter.monitor_adapter.ManagedSystemConnectorFactory"

    @pytest.fixture
    async def event_bus(self):
        """Create an event bus with a large queue size."""
        bus = PolarisEventBus(max_queue_size=10000)
        await bus.start()
        yield bus
        await bus.stop()

    @pytest.fixture
    async def monitor_adapter(self, event_bus):
        """Create a monitor adapter with a fast collection interval."""
        with patch(self.FACTORY_PATH) as MockFactoryClass:
            mock_factory_instance = MagicMock()
            mock_factory_instance.create_connector.return_value = MockFastConnector()
            MockFactoryClass.return_value = mock_factory_instance

            config = AdapterConfiguration(
                adapter_id="perf-test-adapter",
                adapter_type="monitoring",
                config={"collection_interval": 0.1, "max_concurrent_collections": 10}
            )
            
            adapter = MonitorAdapter(
                configuration=config,
                event_bus=event_bus,
                plugin_registry=MagicMock()
            )

            await adapter.start()
            yield adapter
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_high_throughput_metric_collection(self, monitor_adapter):
        """Test the adapter's ability to handle high throughput of metric collections."""
        for i in range(100):
            target = MonitoringTarget(
                system_id=f"system-{i}",
                connector_type="mock",
                collection_interval=0.1,
                config={"collection_mode": MetricCollectionMode.PULL}
            )
            monitor_adapter.add_monitoring_target(target)

        await asyncio.sleep(1.5)

        stats = monitor_adapter.get_collection_statistics()
        total = stats.get("total_collections", 0)
        successful = stats.get("successful_collections", 0)
        assert total > 0, "No collections were performed"
        assert successful > 0, "No successful collections"
        success_rate = successful / total
        assert success_rate > 0.9, f"Success rate {success_rate} is not greater than 0.9"

    @pytest.mark.asyncio
    async def test_backpressure_handling(self, monitor_adapter, event_bus):
        """Test that the adapter handles backpressure correctly when event bus is slow."""
        processed_events = []
        async def slow_handler(event):
            await asyncio.sleep(0.5)
            processed_events.append(event)

        event_bus.subscribe(RealTelemetryEvent, slow_handler)

        target = MonitoringTarget(
            system_id="system-1",
            connector_type="mock",
            collection_interval=0.1,
            config={"collection_mode": MetricCollectionMode.PULL}
        )
        monitor_adapter.add_monitoring_target(target)

        await asyncio.sleep(2.0)

        stats = monitor_adapter.get_collection_statistics()
        assert stats.get("total_collections", 0) > 0
        assert len(processed_events) > 0

    @pytest.mark.asyncio
    async def test_concurrent_collection_limits(self, monitor_adapter):
        """Test that the adapter respects max_concurrent_collections."""
        class SlowConnector(MockFastConnector):
            async def collect_metrics(self):
                await asyncio.sleep(0.5)
                return await super().collect_metrics()

        with patch(self.FACTORY_PATH) as MockFactoryClass:
            mock_slow_factory = MagicMock()
            mock_slow_factory.create_connector.return_value = SlowConnector()
            MockFactoryClass.return_value = mock_slow_factory

            for i in range(15):
                target = MonitoringTarget(
                    system_id=f"slow-system-{i}",
                    connector_type="mock",
                    collection_interval=0.1,
                    config={"collection_mode": MetricCollectionMode.PULL}
                )
                monitor_adapter.add_monitoring_target(target)

            await asyncio.sleep(1.0)

            stats = monitor_adapter.get_collection_statistics()
            assert stats.get("active_collections", 0) <= 10