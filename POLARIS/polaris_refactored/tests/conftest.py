"""
Main pytest configuration file for POLARIS testing framework.

This file configures pytest and provides global fixtures for all tests.
It imports and makes available all the comprehensive testing utilities.
"""

import asyncio
import json
import pytest
from typing import Any, Callable, Dict, List

# Import all fixtures and utilities
try:
    from tests.fixtures.test_fixtures import *
    from tests.fixtures.mock_objects import *
    from tests.fixtures.logging_fixtures import *
    from tests.utils.test_helpers import *
except ImportError:
    # Fallback for when imports fail - provide minimal functionality
    pass


class FakeMessageBroker:
    """In-memory broker used for testing PolarisMessageBus.

    - Tracks connect/disconnect state
    - Stores subscriptions by topic -> callback
    - publish() immediately invokes the subscribed callback(s)
    """

    def __init__(self) -> None:
        self.connected: bool = False
        self.published: List[Dict[str, Any]] = []
        self._subs: Dict[str, Callable[[bytes], None]] = {}
        self._id_counter = 0

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False
        self._subs.clear()

    async def publish(self, topic: str, message: bytes) -> None:
        # record for assertions
        self.published.append({"topic": topic, "message": message})
        # deliver to subscriber if present
        cb = self._subs.get(topic)
        if cb:
            # emulate async callback invocation
            await asyncio.sleep(0)
            cb(message)

    async def subscribe(self, topic: str, handler: Callable[[bytes], None]) -> str:
        self._id_counter += 1
        sub_id = f"sub-{self._id_counter}"
        # only one subscription per topic for simplicity; message_bus multiplexes handlers per topic itself
        self._subs[topic] = handler
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        # Remove any topic that used this subscription id (we don't map id->topic in this simple fake)
        # For test purposes, clear all subs to simulate broker unsubscribed for the topic requested by the bus
        # The bus removes the mapping on its side, so we can be lenient here.
        return None


class FakeMetricsCollector:
    def __init__(self) -> None:
        self.counters: Dict[str, int] = {}

    def increment_counter(self, name: str, labels: Dict[str, str]) -> None:
        self.counters[name] = self.counters.get(name, 0) + 1


# Legacy fixtures for backward compatibility
@pytest.fixture
def fake_broker():
    return FakeMessageBroker()


@pytest.fixture
def metrics_collector():
    return FakeMetricsCollector()


# Pytest configuration hooks
def pytest_configure(config):
    """Configure pytest with custom markers and settings."""
    # Register custom markers
    config.addinivalue_line("markers", "unit: Unit tests that run in isolation")
    config.addinivalue_line("markers", "integration: Integration tests that require external dependencies")
    config.addinivalue_line("markers", "performance: Performance tests that measure system performance")
    config.addinivalue_line("markers", "slow: Tests that take longer than usual to complete")
    config.addinivalue_line("markers", "flaky: Tests that may occasionally fail due to timing issues")


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests"
    )
    parser.addoption(
        "--performance",
        action="store_true",
        default=False,
        help="Run performance tests"
    )
    parser.addoption(
        "--coverage-threshold",
        type=float,
        default=80.0,
        help="Minimum coverage threshold percentage"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle custom markers."""
    # Skip integration tests unless --integration is specified
    if not config.getoption("--integration"):
        skip_integration = pytest.mark.skip(reason="need --integration option to run")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)
    
    # Skip performance tests unless --performance is specified
    if not config.getoption("--performance"):
        skip_performance = pytest.mark.skip(reason="need --performance option to run")
        for item in items:
            if "performance" in item.keywords:
                item.add_marker(skip_performance)


@pytest.fixture(scope="session")
def coverage_threshold(request):
    """Provide the coverage threshold from command line."""
    return request.config.getoption("--coverage-threshold")


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Automatically set up test environment for each test."""
    # This runs before each test
    yield
    # Cleanup after each test if needed
