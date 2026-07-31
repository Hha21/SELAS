"""
Test utilities and helper functions for POLARIS unit testing.

This module provides common testing patterns, assertions, and utilities
to reduce boilerplate and improve test maintainability.
"""

import asyncio
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Type, Union
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.domain.models import SystemState, ExecutionResult


class TestAssertions:
    """Custom assertions for POLARIS testing."""
    
    @staticmethod
    def assert_system_state_valid(state: SystemState) -> None:
        """Assert that a SystemState object is valid."""
        assert state.system_id is not None
        assert state.timestamp is not None
        assert isinstance(state.metrics, dict)
        assert state.health_status is not None
    
    @staticmethod
    def assert_execution_result_valid(result: ExecutionResult) -> None:
        """Assert that an ExecutionResult is valid."""
        assert result.action_id is not None
        assert result.status is not None
        assert isinstance(result.result_data, dict)
        assert result.completed_at is not None
    
    @staticmethod
    def assert_metrics_collected(metrics_collector, metric_name: str, expected_count: int = None) -> None:
        """Assert that specific metrics were collected."""
        if expected_count is not None:
            actual_count = metrics_collector.counters.get(metric_name, 0)
            assert actual_count == expected_count, f"Expected {expected_count} {metric_name} metrics, got {actual_count}"
        else:
            assert metric_name in metrics_collector.counters, f"Metric {metric_name} was not collected"
    
    @staticmethod
    def assert_logs_contain(logger, level: str, message_fragment: str) -> None:
        """Assert that logs contain a specific message at a specific level."""
        matching_logs = [
            log for log in logger.logs 
            if log["level"] == level and message_fragment in log["message"]
        ]
        assert len(matching_logs) > 0, f"No {level} logs found containing '{message_fragment}'"
    
    @staticmethod
    def assert_traces_contain_operation(tracer, operation_name: str) -> None:
        """Assert that traces contain a specific operation."""
        matching_spans = [
            span for span in tracer.spans 
            if span["operation_name"] == operation_name
        ]
        assert len(matching_spans) > 0, f"No traces found for operation '{operation_name}'"
    
    @staticmethod
    def assert_telemetry_event_valid(event) -> None:
        """Assert that a TelemetryEvent is valid."""
        from src.framework.events import TelemetryEvent
        
        assert isinstance(event, TelemetryEvent), f"Expected TelemetryEvent, got {type(event)}"
        assert event.event_id is not None, "TelemetryEvent must have an event_id"
        assert event.timestamp is not None, "TelemetryEvent must have a timestamp"
        assert event.system_id is not None, "TelemetryEvent must have a system_id"
        assert event.system_state is not None, "TelemetryEvent must have a system_state"
        
        # Validate the system state
        TestAssertions.assert_system_state_valid(event.system_state)


class AsyncTestHelper:
    """Helper for async testing patterns."""
    
    @staticmethod
    async def wait_for_condition(
        condition: Callable[[], bool], 
        timeout: float = 5.0, 
        interval: float = 0.1
    ) -> bool:
        """Wait for a condition to become true within a timeout."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if condition():
                return True
            await asyncio.sleep(interval)
        return False
    
    @staticmethod
    async def wait_for_async_condition(
        condition: Callable[[], bool], 
        timeout: float = 5.0, 
        interval: float = 0.1
    ) -> bool:
        """Wait for an async condition to become true within a timeout."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if await condition():
                return True
            await asyncio.sleep(interval)
        return False
    
    @staticmethod
    @asynccontextmanager
    async def timeout_context(timeout: float):
        """Context manager for async operations with timeout."""
        try:
            await asyncio.wait_for(asyncio.sleep(0), timeout=timeout)
            yield
        except asyncio.TimeoutError:
            pytest.fail(f"Operation timed out after {timeout} seconds")
    
    @staticmethod
    async def run_with_timeout(coro, timeout: float = 5.0):
        """Run a coroutine with a timeout."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            pytest.fail(f"Coroutine timed out after {timeout} seconds")


class MockHelper:
    """Helper for creating and managing mocks."""
    
    @staticmethod
    def create_async_mock_with_return_value(return_value: Any) -> AsyncMock:
        """Create an AsyncMock that returns a specific value."""
        mock = AsyncMock()
        mock.return_value = return_value
        return mock
    
    @staticmethod
    def create_async_mock_with_side_effect(side_effect: Union[Exception, List[Any]]) -> AsyncMock:
        """Create an AsyncMock with a side effect."""
        mock = AsyncMock()
        mock.side_effect = side_effect
        return mock
    
    @staticmethod
    def create_mock_with_attributes(**attributes) -> MagicMock:
        """Create a MagicMock with specific attributes."""
        mock = MagicMock()
        for name, value in attributes.items():
            setattr(mock, name, value)
        return mock
    
    @staticmethod
    @contextmanager
    def patch_multiple(target_module: str, **patches):
        """Context manager for patching multiple objects in a module."""
        with patch.multiple(target_module, **patches) as mocks:
            yield mocks


class PerformanceTestHelper:
    """Helper for performance testing."""
    
    @staticmethod
    @contextmanager
    def measure_time():
        """Context manager to measure execution time."""
        start_time = time.time()
        result = {"duration": None}
        try:
            yield result
        finally:
            result["duration"] = time.time() - start_time
    
    @staticmethod
    async def measure_async_time(coro):
        """Measure the execution time of an async operation."""
        start_time = time.time()
        result = await coro
        duration = time.time() - start_time
        return result, duration
    
    @staticmethod
    def assert_performance_within_bounds(duration: float, max_duration: float) -> None:
        """Assert that an operation completed within performance bounds."""
        assert duration <= max_duration, f"Operation took {duration:.3f}s, expected <= {max_duration:.3f}s"
    
    @staticmethod
    async def run_load_test(
        operation: Callable, 
        concurrent_requests: int, 
        total_requests: int
    ) -> Dict[str, Any]:
        """Run a simple load test on an operation."""
        semaphore = asyncio.Semaphore(concurrent_requests)
        
        async def limited_operation():
            async with semaphore:
                start_time = time.time()
                try:
                    result = await operation()
                    return {"success": True, "duration": time.time() - start_time, "result": result}
                except Exception as e:
                    return {"success": False, "duration": time.time() - start_time, "error": str(e)}
        
        start_time = time.time()
        results = await asyncio.gather(*[limited_operation() for _ in range(total_requests)])
        total_duration = time.time() - start_time
        
        successful_results = [r for r in results if r["success"]]
        failed_results = [r for r in results if not r["success"]]
        
        return {
            "total_requests": total_requests,
            "successful_requests": len(successful_results),
            "failed_requests": len(failed_results),
            "success_rate": len(successful_results) / total_requests,
            "total_duration": total_duration,
            "requests_per_second": total_requests / total_duration,
            "avg_response_time": sum(r["duration"] for r in successful_results) / len(successful_results) if successful_results else 0,
            "max_response_time": max(r["duration"] for r in successful_results) if successful_results else 0,
            "min_response_time": min(r["duration"] for r in successful_results) if successful_results else 0
        }


class DataTestHelper:
    """Helper for data-related testing."""
    
    @staticmethod
    def create_test_metrics(count: int = 5) -> Dict[str, Any]:
        """Create test metrics data."""
        metrics = {}
        for i in range(count):
            metrics[f"metric_{i}"] = {
                "value": float(i * 10),
                "unit": "percent" if i % 2 == 0 else "MB",
                "timestamp": datetime.now()
            }
        return metrics
    
    @staticmethod
    def create_test_system_states(system_ids: List[str]) -> List[SystemState]:
        """Create test system states for multiple systems."""
        from tests.fixtures.mock_objects import TestDataBuilder
        return [
            TestDataBuilder.system_state(system_id=system_id)
            for system_id in system_ids
        ]
    
    @staticmethod
    def assert_data_consistency(data1: Dict[str, Any], data2: Dict[str, Any], ignore_keys: List[str] = None) -> None:
        """Assert that two data dictionaries are consistent, ignoring specified keys."""
        ignore_keys = ignore_keys or []
        
        filtered_data1 = {k: v for k, v in data1.items() if k not in ignore_keys}
        filtered_data2 = {k: v for k, v in data2.items() if k not in ignore_keys}
        
        assert filtered_data1 == filtered_data2, f"Data inconsistency found: {filtered_data1} != {filtered_data2}"


class EventTestHelper:
    """Helper for event-related testing."""
    
    @staticmethod
    async def wait_for_event_publication(
        message_broker, 
        expected_topic: str, 
        timeout: float = 5.0
    ) -> bool:
        """Wait for an event to be published to a specific topic."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            for message in message_broker.published_messages:
                if message["topic"] == expected_topic:
                    return True
            await asyncio.sleep(0.1)
        return False
    
    @staticmethod
    def assert_event_published(message_broker, topic: str, message_content: str = None) -> None:
        """Assert that an event was published to a specific topic."""
        matching_messages = [
            msg for msg in message_broker.published_messages
            if msg["topic"] == topic
        ]
        assert len(matching_messages) > 0, f"No messages published to topic '{topic}'"
        
        if message_content:
            content_found = any(
                message_content in str(msg["message"])
                for msg in matching_messages
            )
            assert content_found, f"Message content '{message_content}' not found in published messages"
    
    @staticmethod
    async def simulate_event_sequence(
        event_publisher: Callable,
        events: List[Any],
        delay_between_events: float = 0.1
    ) -> None:
        """Simulate a sequence of events with delays."""
        for event in events:
            await event_publisher(event)
            await asyncio.sleep(delay_between_events)


class ConfigTestHelper:
    """Helper for configuration testing."""
    
    @staticmethod
    def create_test_config(**overrides) -> Dict[str, Any]:
        """Create a test configuration with optional overrides."""
        default_config = {
            "framework": {
                "name": "polaris_test",
                "version": "1.0.0",
                "log_level": "DEBUG"
            },
            "adapters": {
                "monitor": {
                    "collection_interval": 1.0,
                    "batch_size": 10
                },
                "execution": {
                    "timeout": 30.0,
                    "retry_attempts": 3
                }
            },
            "infrastructure": {
                "message_broker": {
                    "url": "nats://localhost:4222",
                    "timeout": 5.0
                },
                "data_store": {
                    "type": "memory",
                    "connection_string": "memory://"
                }
            }
        }
        
        # Apply overrides
        for key, value in overrides.items():
            if "." in key:
                # Handle nested keys like "framework.log_level"
                keys = key.split(".")
                current = default_config
                for k in keys[:-1]:
                    if k not in current:
                        current[k] = {}
                    current = current[k]
                current[keys[-1]] = value
            else:
                default_config[key] = value
        
        return default_config
    
    @staticmethod
    def assert_config_valid(config: Dict[str, Any], required_keys: List[str]) -> None:
        """Assert that a configuration contains all required keys."""
        for key in required_keys:
            if "." in key:
                keys = key.split(".")
                current = config
                for k in keys:
                    assert k in current, f"Required config key '{key}' not found"
                    current = current[k]
            else:
                assert key in config, f"Required config key '{key}' not found"


# Decorator for marking tests that require specific conditions
def requires_integration_environment(func):
    """Decorator to skip tests that require integration environment."""
    return pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration environment not available"
    )(func)


def requires_performance_environment(func):
    """Decorator to skip tests that require performance testing environment."""
    return pytest.mark.skipif(
        not pytest.config.getoption("--performance", default=False),
        reason="Performance testing environment not available"
    )(func)


# Custom pytest markers
pytest_markers = {
    "unit": "Unit tests that run in isolation",
    "integration": "Integration tests that require external dependencies",
    "performance": "Performance tests that measure system performance",
    "slow": "Tests that take longer than usual to complete",
    "flaky": "Tests that may occasionally fail due to timing issues"
}