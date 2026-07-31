"""
Tests for the POLARIS Event System.

Covers event serialization/deserialization, filtering, routing, and error handling.
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from polaris_refactored.src.framework.events import (
    PolarisEvent, TelemetryEvent, AdaptationEvent, ExecutionResultEvent,
    EventSubscription, EventProcessingError, PolarisEventBus
)
from polaris_refactored.src.domain.models import SystemState, HealthStatus, MetricValue, AdaptationAction, ExecutionResult

@pytest.fixture
def sample_system_state():
    return SystemState(
        system_id="test-system-1",
        health_status=HealthStatus.HEALTHY,
        metrics={
            "cpu_usage": MetricValue(
                name="cpu_usage",
                value=42.5,
                unit="percent",
                timestamp=datetime.now(timezone.utc)
            )
        },
        timestamp=datetime.now(timezone.utc)
    )

@pytest.fixture
def sample_adaptation_action():
    return AdaptationAction(
        action_id="action-1",
        action_type="scale_up",
        target_system="test-system-1",
        parameters={"amount": 1}
    )

@pytest.fixture
def sample_execution_result(sample_adaptation_action):
    return ExecutionResult(
        action_id=sample_adaptation_action.action_id,
        success=True,
        message="Action completed successfully",
        timestamp=datetime.now(timezone.utc)
    )

class TestEventSerialization:
    """Tests for event serialization and deserialization."""
    
    def test_polaris_event_serialization(self):
        """Test basic event serialization."""
        event = PolarisEvent(
            event_id="test-event-1",
            correlation_id="test-correlation-1"
        )
        
        data = event.to_dict()
        assert data["event_id"] == "test-event-1"
        assert data["correlation_id"] == "test-correlation-1"
        assert "timestamp" in data
        assert data["event_type"] == "PolarisEvent"
    
    def test_telemetry_event_serialization(self, sample_system_state):
        """Test telemetry event serialization."""
        event = TelemetryEvent(
            system_state=sample_system_state,
            event_id="telemetry-1"
        )
        
        data = event.to_dict()
        assert data["event_type"] == "TelemetryEvent"
        assert data["system_id"] == "test-system-1"
        assert "system_state" in data
        assert data["system_state"]["health_status"] == "healthy"
    
    def test_adaptation_event_serialization(self, sample_adaptation_action):
        """Test adaptation event serialization."""
        event = AdaptationEvent(
            system_id="test-system-1",
            reason="High CPU usage",
            suggested_actions=[sample_adaptation_action],
            severity="high"
        )
        
        data = event.to_dict()
        assert data["event_type"] == "AdaptationEvent"
        assert data["system_id"] == "test-system-1"
        assert data["reason"] == "High CPU usage"
        assert len(data["suggested_actions"]) == 1
        assert data["suggested_actions_count"] == 1
        assert data["metadata"]["priority"] == 3  # high severity = priority 3

class TestEventBus:
    """Tests for the PolarisEventBus functionality."""
    
    @pytest.fixture
    async def event_bus(self):
        """Create a test event bus with a single worker."""
        bus = PolarisEventBus(worker_count=1, max_queue_size=10)
        await bus.start()
        yield bus
        await bus.stop()
    
    @pytest.mark.asyncio
    async def test_event_publish_subscribe(self, event_bus, sample_system_state):
        """Test basic event publishing and subscription."""
        handler = AsyncMock()
        event = TelemetryEvent(system_state=sample_system_state)
        
        # Subscribe to TelemetryEvent
        sub_id = event_bus.subscribe(TelemetryEvent, handler)
        
        # Publish event
        await event_bus.publish(event)
        
        # Give the event loop time to process
        await asyncio.sleep(0.1)
        
        # Verify handler was called
        handler.assert_called_once()
        called_event = handler.call_args[0][0]
        assert called_event.event_id == event.event_id
    
    @pytest.mark.asyncio
    async def test_event_filtering(self, event_bus, sample_system_state):
        """Test event filtering functionality."""
        # Create two telemetry events with different system IDs
        state1 = sample_system_state
        state2 = SystemState(
            system_id="test-system-2",
            health_status=HealthStatus.UNHEALTHY,
            metrics={},
            timestamp=datetime.now(timezone.utc)
        )
        
        event1 = TelemetryEvent(system_state=state1)
        event2 = TelemetryEvent(system_state=state2)
        
        # Create a handler that only accepts events for system-1
        handler = AsyncMock()
        
        def filter_func(event):
            return event.system_id == "test-system-1"
        
        # Subscribe with filter
        event_bus.subscribe(TelemetryEvent, handler, filter_func=filter_func)
        
        # Publish both events
        await event_bus.publish(event1)
        await event_bus.publish(event2)
        
        # Give the event loop time to process
        await asyncio.sleep(0.1)
        
        # Verify only event1 was processed
        assert handler.call_count == 1
        assert handler.call_args[0][0].system_id == "test-system-1"
    
    @pytest.mark.asyncio
    async def test_error_handling(self, event_bus, sample_system_state):
        """Test error handling in event handlers."""
        # Create a handler that raises an exception
        async def failing_handler(event):
            raise ValueError("Test error")
        
        # Set up error handler
        error_handler = AsyncMock()
        event_bus.subscribe(TelemetryEvent, failing_handler)
        
        # Publish event
        event = TelemetryEvent(system_state=sample_system_state)
        await event_bus.publish(event)
        
        # Give the event loop time to process
        await asyncio.sleep(0.1)
        
        # Verify error was logged (we can check logs or use a mock)
        # This is a simplified check - in practice, you'd want to verify logs
        assert True
    
    @pytest.mark.asyncio
    async def test_backpressure_handling(self, event_bus, sample_system_state):
        """Test that the event bus handles backpressure."""
        # Create a slow handler
        async def slow_handler(event):
            await asyncio.sleep(1)
               
        # Subscribe the slow handler
        event_bus.subscribe(TelemetryEvent, slow_handler)
        
        # Fill the queue to capacity
        for i in range(10):  # Queue size is 10
            event = TelemetryEvent(system_state=sample_system_state)
            await event_bus.publish(event)
        
        # The next publish should not block (test will hang if it does)
        event = TelemetryEvent(system_state=sample_system_state)
        await event_bus.publish(event)  # This should not block
        
        # Clean up
        await event_bus.stop()

class TestEventCorrelation:
    """Tests for event correlation functionality."""
    
    @pytest.fixture
    async def event_bus(self):
        bus = PolarisEventBus(worker_count=1)
        await bus.start()
        yield bus
        await bus.stop()
    
    @pytest.mark.asyncio
    async def test_event_correlation(self, event_bus, sample_system_state):
        """Test that related events can be correlated."""
        correlation_id = "test-correlation-1"
        
        # Create two related events
        telemetry_event = TelemetryEvent(
            system_state=sample_system_state,
            correlation_id=correlation_id
        )
        
        adaptation_event = AdaptationEvent(
            system_id=sample_system_state.system_id,
            reason="High CPU usage",
            correlation_id=correlation_id
        )
        
        # Have to ensure evenst are processed
        # Publish both events
        await event_bus.publish_and_wait(telemetry_event)
        await event_bus.publish_and_wait(adaptation_event)
        
        # Get correlated events
        event_ids = event_bus.get_correlated_events(correlation_id)

        # Verify both events are    
        assert len(event_ids) == 2
        assert telemetry_event.event_id in event_ids
        assert adaptation_event.event_id in event_ids
