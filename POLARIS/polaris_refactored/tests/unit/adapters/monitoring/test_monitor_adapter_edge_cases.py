"""
Edge Case Tests for Monitor Adapter

Tests for error conditions, timeouts, and unusual scenarios in the Monitor Adapter.
"""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from unittest import mock
from unittest.mock import AsyncMock, patch, MagicMock, DEFAULT

from polaris_refactored.src.adapters.monitor_adapter import (
    MonitorAdapter,
    MetricCollectionStrategy,
    DirectConnectorStrategy,
    PollingStrategy,
    BatchCollectionStrategy,
    MonitoringTarget,
    CollectionResult,
    MetricCollectionMode
)
from polaris_refactored.src.adapters.base_adapter import AdapterConfiguration, AdapterValidationError
from polaris_refactored.src.framework.events import PolarisEventBus, TelemetryEvent
from polaris_refactored.src.domain.models import MetricValue, SystemState, HealthStatus
from polaris_refactored.src.domain.interfaces import ManagedSystemConnector

class FailingConnector(ManagedSystemConnector):
    """A connector that fails in various ways for testing error handling."""
    
    def __init__(self, system_id: str = "test-system", fail_mode: str = None):
        self._system_id = system_id
        self.fail_mode = fail_mode
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.collect_calls = 0
        self.state_calls = 0
    
    async def connect(self) -> bool:
        self.connect_calls += 1
        if self.fail_mode == "connect":
            raise ConnectionError("Failed to connect")
        return True
    
    async def disconnect(self) -> bool:
        self.disconnect_calls += 1
        if self.fail_mode == "disconnect":
            raise RuntimeError("Failed to disconnect")
        return True
    
    async def get_system_id(self) -> str:
        return self._system_id
    
    async def collect_metrics(self) -> dict:
        self.collect_calls += 1
        if self.fail_mode == "collect":
            raise RuntimeError("Failed to collect metrics")
        elif self.fail_mode == "timeout":
            # Simulate a very long collection; callers can wrap with wait_for if desired
            await asyncio.sleep(10)
        return {"cpu_usage": MetricValue("cpu_usage", 50.0, "percent")}
    
    async def get_system_state(self) -> SystemState:
        self.state_calls += 1
        if self.fail_mode == "get_state":
            raise RuntimeError("Failed to get system state")
        return SystemState(
            system_id=self._system_id,
            timestamp=datetime.now(timezone.utc),
            metrics={"dummy": MetricValue("dummy", 1, "count")},
            health_status=HealthStatus.HEALTHY
        )
    
    async def execute_action(self, action):
        if self.fail_mode == "execute":
            raise RuntimeError("Execution failed")
        return {"status": "success"}
    
    async def validate_action(self, action):
        return True
    
    async def get_supported_actions(self):
        return ["test_action"]

class FailingStrategy(MetricCollectionStrategy):
    """A strategy that fails in various ways for testing."""
    
    def __init__(self, fail_mode: str = None):
        self.fail_mode = fail_mode
        self.collect_calls = []
    
    def get_strategy_name(self) -> str:
        return "failing_strategy"
    
    def supports_target(self, target) -> bool:
        if self.fail_mode == "unsupported":
            return False
        return True
    
    async def collect_metrics(self, target, connector_factory) -> CollectionResult:
        self.collect_calls.append(target.system_id)
        
        if self.fail_mode == "collect":
            # Return a failure result instead of raising to align with adapter expectations
            return CollectionResult(
                system_id=target.system_id,
                metrics={},
                timestamp=datetime.now(timezone.utc),
                success=False,
                error="Strategy collection failed",
            )
        elif self.fail_mode == "timeout":
            await asyncio.sleep(10)
        
        return CollectionResult(
            system_id=target.system_id,
            metrics={"cpu_usage": MetricValue("cpu_usage", 50.0, "percent")},
            timestamp=datetime.now(timezone.utc),
            success=True
        )

@pytest.fixture
async def event_bus():
    """Fixture providing a PolarisEventBus instance."""
    bus = PolarisEventBus()
    await bus.start()
    yield bus
    await bus.stop()

@pytest.fixture
def valid_config():
    """Fixture providing a valid adapter configuration."""
    return AdapterConfiguration(
        adapter_id="monitor-test",
        adapter_type="monitor",
        enabled=True,
        config={
            "collection_interval_seconds": 1,
            "max_concurrent_collections": 5,
            "collection_timeout_seconds": 2,
            "collection_mode": "pull",
            "targets": [
                {
                    "system_id": "test-system",
                    "connector_type": "test-connector",
                    "collection_mode": "pull",
                    "collection_interval_seconds": 1,
                    "enabled": True
                }
            ]
        }
    )

@pytest.fixture
def mock_plugin_registry():
    """Fixture providing a plugin registry compatible with ManagedSystemConnectorFactory."""
    class MockRegistry:
        def __init__(self):
            # Map of system_id (we use connector_type as key) -> connector instance
            self._connectors: dict[str, ManagedSystemConnector] = {}

        def register_connector(self, key: str, connector: ManagedSystemConnector):
            self._connectors[key] = connector

        def load_managed_system_connector(self, system_id: str):
            # Factory passes connector_type as system_id
            return self._connectors.get(system_id)

        # Optional helper methods used by factory; keep stubs minimal
        def get_plugin_descriptors(self):
            return {}

        def is_plugin_loaded(self, system_id: str) -> bool:
            return system_id in self._connectors

    return MockRegistry()

@pytest.mark.asyncio
async def test_connector_collection_failure(valid_config, event_bus, mock_plugin_registry):
    """Test handling of connector collection failure via DirectConnectorStrategy."""
    # Register a connector keyed by connector_type used in target
    connector = FailingConnector(fail_mode="collect")
    mock_plugin_registry.register_connector("test-connector", connector)

    adapter = MonitorAdapter(
        configuration=valid_config,
        event_bus=event_bus,
        plugin_registry=mock_plugin_registry,
    )

    await adapter._validate_configuration()
    await adapter._initialize_resources()

    # Build a target and invoke collection
    target = MonitoringTarget(
        system_id="test-system",
        connector_type="test-connector",
        collection_interval=0.1,
        enabled=True,
    )

    result = await adapter._collect_target_metrics(target)
    assert result.success is False
    assert "Failed to collect" in (result.error or "")

@pytest.mark.asyncio
async def test_metric_collection_timeout_simulated(valid_config, event_bus, mock_plugin_registry):
    """Simulate a timeout by having connector block; ensure failure is returned when wrapped by strategy."""
    connector = FailingConnector(fail_mode="timeout")
    mock_plugin_registry.register_connector("test-connector", connector)

    adapter = MonitorAdapter(
        configuration=valid_config,
        event_bus=event_bus,
        plugin_registry=mock_plugin_registry,
    )

    await adapter._validate_configuration()
    await adapter._initialize_resources()

    target = MonitoringTarget(
        system_id="test-system",
        connector_type="test-connector",
        collection_interval=0.1,
        enabled=True,
    )

    # Run the direct strategy but wrap the call in wait_for to simulate external timeout
    try:
        await asyncio.wait_for(adapter._collect_target_metrics(target), timeout=0.05)
        assert False, "Expected timeout did not occur"
    except asyncio.TimeoutError:
        assert True

@pytest.mark.asyncio
async def test_strategy_failure_handling(valid_config, event_bus, mock_plugin_registry):
    """Test handling of strategy failures."""
    # Create a working connector
    connector = FailingConnector()
    # Register under connector_type key used in the target below
    mock_plugin_registry.register_connector("test-connector", connector)
    
    # Create a failing strategy that returns a failure result
    failing_strategy = FailingStrategy(fail_mode="collect")

    # Create adapter with custom strategy
    adapter = MonitorAdapter(
        configuration=valid_config,
        event_bus=event_bus,
        plugin_registry=mock_plugin_registry
    )
    
    await adapter._validate_configuration()
    await adapter._initialize_resources()
    # Register the failing strategy in the adapter
    adapter._collection_strategies = {failing_strategy.get_strategy_name(): failing_strategy}
    
    # Collect metrics - should handle the strategy failure
    result = await adapter._collect_target_metrics(
        MonitoringTarget(
            system_id="test-system",
            connector_type="test-connector",
            collection_interval=0.1,
            enabled=True,
            config={"collection_strategy": failing_strategy.get_strategy_name()},
        )
    )
    
    assert not result.success
    assert "Strategy collection failed" in result.error
    assert len(failing_strategy.collect_calls) == 1

@pytest.mark.asyncio
async def test_target_validation_failures(valid_config, event_bus, mock_plugin_registry):
    """Test handling of invalid target configurations: expect AdapterValidationError."""
    # Create adapter with invalid monitoring_targets config type
    config = AdapterConfiguration(
        adapter_id=valid_config.adapter_id,
        adapter_type=valid_config.adapter_type,
        enabled=True,
        config={
            "collection_mode": "pull",
            "monitoring_targets": [
                {
                    # Missing connector_type should trigger validation error
                    "system_id": "invalid-target",
                    "enabled": True,
                }
            ]
        },
    )

    adapter = MonitorAdapter(
        configuration=config,
        event_bus=event_bus,
        plugin_registry=mock_plugin_registry,
    )

    with pytest.raises(AdapterValidationError):
        await adapter._validate_configuration()

@pytest.mark.asyncio
async def test_event_publishing_errors(valid_config, event_bus, mock_plugin_registry):
    """Test handling of event publishing errors."""
    # Create a mock connector that will be returned by the factory
    mock_connector = AsyncMock()
    mock_connector.collect_metrics.return_value = CollectionResult(
        system_id="test-system",
        metrics={"test_metric": 42},
        timestamp=datetime.now(timezone.utc),
        success=True
    )
    
    # Register the mock connector so factory resolves it via plugin registry
    mock_plugin_registry.register_connector("test-connector", mock_connector)
    
    # Create a mock event bus that raises an exception on publish_telemetry
    mock_bus = AsyncMock(spec=type(event_bus))
    
    # Track if publish_telemetry was called
    publish_called = asyncio.Future()
    
    # Create a side effect that completes our future and raises
    async def raise_and_notify(*args, **kwargs):
        if not publish_called.done():
            publish_called.set_result(True)
        raise Exception("Failed to publish event")
    
    # Configure the mock bus
    mock_bus.start = AsyncMock(return_value=None)
    mock_bus.stop = AsyncMock(return_value=None)
    mock_bus.publish_telemetry = AsyncMock(side_effect=raise_and_notify)
    
    # Create adapter with mock event bus and plugin registry
    adapter = MonitorAdapter(
        configuration=valid_config,
        event_bus=mock_bus,
        plugin_registry=mock_plugin_registry
    )
    
    # Create a test target
    target = MonitoringTarget(
        system_id="test-system",
        connector_type="test-connector",
        collection_interval=0.1,
        enabled=True
    )
    
    # Manually add the target to the adapter
    adapter._monitoring_targets[target.system_id] = target
    
    # Start the adapter
    await adapter.start()
    
    try:
        # Wait for publish_telemetry to be called or timeout after 2 seconds
        try:
            await asyncio.wait_for(publish_called, timeout=2.0)
            # Verify the event was published (even though it failed)
            assert mock_bus.publish_telemetry.called, "publish_telemetry should have been called"
        except asyncio.TimeoutError:
            assert False, "publish_telemetry was not called within timeout"
    finally:
        # Stop adapter to cleanup tasks
        await adapter.stop()
    # Note: adaptive interval behavior is covered in test_monitor_adapter.py
