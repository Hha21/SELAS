# POLARIS Testing Infrastructure

This directory contains the comprehensive testing infrastructure for the POLARIS framework, providing unit tests, integration tests, performance tests, and testing utilities.

## Overview

The POLARIS testing infrastructure is designed to ensure high code quality, reliability, and performance. It includes:

- **Unit Testing Framework**: Isolated testing with dependency injection and comprehensive mocking
- **Integration Testing Harness**: Component interaction testing with real and mock dependencies
- **Performance Testing Suite**: Throughput, latency, and scalability testing with benchmarking
- **Contract Testing**: Interface compliance validation for ManagedSystemConnector implementations
- **Test Utilities**: Common testing patterns, assertions, and helper functions

## Directory Structure

```
tests/
├── README.md                          # This file
├── conftest.py                        # Global pytest configuration and fixtures
├── run_tests.py                       # Main test runner with multiple modes
│
├── fixtures/                          # Test fixtures and mock objects
│   ├── __init__.py
│   ├── mock_objects.py               # Comprehensive mock implementations
│   └── test_fixtures.py              # Pytest fixtures for dependency injection
│
├── utils/                            # Testing utilities and helpers
│   ├── __init__.py
│   ├── test_helpers.py               # Common testing patterns and assertions
│   └── coverage_utils.py             # Coverage analysis and reporting tools
│
├── unit/                             # Unit tests
│   ├── __init__.py
│   ├── framework/                    # Framework layer tests
│   ├── adapters/                     # Adapter layer tests
│   ├── digital_twin/                 # Digital twin layer tests
│   ├── control_reasoning/            # Control & reasoning layer tests
│   ├── infrastructure/               # Infrastructure layer tests
│   └── domain/                       # Domain model tests
│
├── integration/                      # Integration tests
│   ├── __init__.py
│   ├── harness/                      # Integration test harness
│   │   ├── __init__.py
│   │   └── polaris_integration_test_harness.py
│   ├── contracts/                    # Contract tests
│   │   ├── __init__.py
│   │   └── managed_system_connector_contract.py
│   ├── scenarios/                    # End-to-end test scenarios
│   │   ├── __init__.py
│   │   └── end_to_end_scenarios.py
│   └── test_integration_harness_demo.py
│
├── performance/                      # Performance tests
│   ├── __init__.py
│   ├── polaris_performance_test_suite.py
│   ├── test_performance_benchmarks.py
│   └── run_performance_tests.py
│
└── e2e/                             # End-to-end tests (existing)
    └── ...
```

## Quick Start

### Running Tests

```bash
# Run all unit tests with coverage
python -m tests.run_tests --unit

# Run integration tests
python -m tests.run_tests --integration

# Run performance tests
python -m tests.run_tests --performance

# Run all tests
python -m tests.run_tests --all

# Run specific test file
python -m tests.run_tests --test tests/unit/framework/test_configuration.py

# Run with coverage analysis
python -m tests.run_tests --coverage

# Create test templates for untested modules
python -m tests.run_tests --create-templates
```

### Performance Testing

```bash
# Quick performance check
python -m tests.performance.run_performance_tests --quick

# Throughput benchmark
python -m tests.performance.run_performance_tests --throughput --duration 60 --users 20

# Comprehensive performance suite
python -m tests.performance.run_performance_tests --comprehensive
```

## Unit Testing Framework

### Features

- **Dependency Injection**: All components use DI for easy mocking and isolation
- **Comprehensive Mocking**: Mock implementations for all major POLARIS components
- **Test Data Builders**: Convenient builders for creating test data objects
- **Custom Assertions**: POLARIS-specific assertions for common validation patterns
- **Async Testing Support**: Full support for async/await testing patterns
- **Parametrized Testing**: Easy parametrized tests for multiple scenarios

### Example Unit Test

```python
import pytest
from tests.fixtures.test_fixtures import *
from tests.utils.test_helpers import TestAssertions, AsyncTestHelper

class TestMyComponent:
    def test_initialization(self, mock_logger, mock_metrics_collector):
        """Test component initialization."""
        component = MyComponent(mock_logger, mock_metrics_collector)
        assert component is not None
    
    @pytest.mark.asyncio
    async def test_async_operation(self, mock_connector):
        """Test async operations."""
        result = await component.process_data(mock_connector)
        TestAssertions.assert_execution_result_valid(result)
    
    @pytest.mark.parametrize("input_value,expected", [
        (10, 20),
        (5, 10),
        (0, 0)
    ])
    def test_calculation(self, input_value, expected):
        """Test calculations with different inputs."""
        result = component.calculate(input_value)
        assert result == expected
```

### Mock Objects

The testing framework provides comprehensive mock implementations:

- `MockManagedSystemConnector`: Mock connector for testing system integrations
- `MockMessageBroker`: In-memory message broker for event testing
- `MockDataStore`: In-memory data store for persistence testing
- `MockMetricsCollector`: Mock metrics collection for observability testing
- `MockLogger`: Mock logger for logging validation
- `MockTracer`: Mock tracer for distributed tracing testing

## Integration Testing Harness

### Features

- **Component Lifecycle Management**: Automatic setup and teardown of POLARIS components
- **Test Environment Isolation**: Each test runs in an isolated environment
- **Mock and Real Component Integration**: Support for both mock and real infrastructure
- **Event Flow Validation**: Comprehensive event monitoring and validation
- **Performance Measurement**: Built-in performance monitoring during integration tests
- **Failure Scenario Testing**: Easy configuration of failure modes for resilience testing

### Example Integration Test

```python
import pytest
from tests.integration.harness.polaris_integration_test_harness import create_simple_harness
from tests.fixtures.mock_objects import TestDataBuilder
from src.domain.models import MetricValue

@pytest.mark.asyncio
@pytest.mark.integration
async def test_telemetry_processing_workflow():
    """Test complete telemetry processing workflow."""
    async with create_simple_harness("telemetry_test", ["web_server", "database"]) as harness:
        # Inject telemetry data
        metrics = {
            "cpu_usage": MetricValue(value=75.0, unit="percent", timestamp=datetime.now())
        }
        await harness.inject_telemetry("web_server", metrics)
        
        # Wait for processing
        events = await harness.wait_for_events("telemetry", 1, timeout=5.0)
        
        # Validate results
        assert len(events) == 1
        harness.assert_no_errors_logged()
```

### Contract Testing

Contract tests ensure that all ManagedSystemConnector implementations meet the interface requirements:

```python
from tests.integration.contracts.managed_system_connector_contract import validate_connector_contract

async def test_my_connector_contract():
    """Test that MyConnector meets the contract requirements."""
    def create_connector():
        return MyConnector("test_system")
    
    is_compliant = await validate_connector_contract(
        connector_factory=create_connector,
        system_id="test_system",
        is_real=True  # Set to False for mock connectors
    )
    
    assert is_compliant, "Connector should be fully contract compliant"
```

## Performance Testing Suite

### Features

- **Throughput Testing**: Measure operations per second under various loads
- **Latency Measurement**: Detailed latency statistics (avg, P50, P95, P99)
- **Load Generation**: Configurable load patterns with ramp-up/ramp-down
- **Stress Testing**: High-load testing to find breaking points
- **Scalability Testing**: Performance testing with increasing system counts
- **Endurance Testing**: Long-duration testing for stability validation
- **Performance Regression Detection**: Automated detection of performance regressions
- **Comprehensive Reporting**: Detailed reports with charts and analysis

### Example Performance Test

```python
import pytest
from tests.performance.polaris_performance_test_suite import (
    PolarisPerformanceTestSuite, LoadTestConfig, PerformanceThresholds
)

@pytest.mark.asyncio
@pytest.mark.performance
async def test_throughput_benchmark():
    """Test system throughput under load."""
    systems = ["perf_system_1", "perf_system_2"]
    suite = PolarisPerformanceTestSuite()
    
    config = LoadTestConfig(
        test_name="throughput_test",
        duration=60.0,
        concurrent_users=20,
        target_throughput=100.0
    )
    
    thresholds = PerformanceThresholds(
        min_throughput=50.0,
        max_avg_latency=0.1,
        max_error_rate=5.0
    )
    
    metrics, passed = await suite.run_throughput_test(systems, config, thresholds)
    
    assert passed, f"Performance test failed: {metrics.error_rate}% error rate"
    assert metrics.throughput >= 50.0, f"Throughput {metrics.throughput} below threshold"
```

## Test Configuration

### pytest.ini Configuration

The testing framework is configured in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = ["-v", "--tb=short"]
filterwarnings = [
    "ignore::DeprecationWarning",
    "ignore::PendingDeprecationWarning",
]

[tool.coverage.run]
source = ["src"]
omit = [
    "*/tests/*",
    "*/test_*",
    "*/__pycache__/*",
    "*/.*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "if self.debug:",
    "raise AssertionError",
    "raise NotImplementedError",
    "if 0:",
    "if __name__ == .__main__.:",
    "class .*\\bProtocol\\):",
    "@(abc\\.)?abstractmethod",
]
```

### Custom Markers

The framework defines custom pytest markers:

- `@pytest.mark.unit`: Unit tests that run in isolation
- `@pytest.mark.integration`: Integration tests requiring external dependencies
- `@pytest.mark.performance`: Performance tests measuring system performance
- `@pytest.mark.slow`: Tests that take longer than usual to complete
- `@pytest.mark.flaky`: Tests that may occasionally fail due to timing issues

### Command Line Options

- `--integration`: Run integration tests
- `--performance`: Run performance tests
- `--coverage-threshold`: Set minimum coverage threshold percentage

## Coverage Requirements

The testing framework enforces a minimum of **80% code coverage** across all modules. Coverage analysis includes:

- Line coverage measurement
- Branch coverage analysis
- Module-level coverage reporting
- Identification of untested files
- Automated test template generation for missing tests

### Coverage Analysis

```bash
# Run coverage analysis
python -m tests.utils.coverage_utils --analyze

# Create test templates for untested modules
python -m tests.utils.coverage_utils --create-templates

# Set custom coverage threshold
python -m tests.utils.coverage_utils --analyze --threshold 85.0
```

## Best Practices

### Unit Testing

1. **Use Dependency Injection**: All components should use DI for easy testing
2. **Mock External Dependencies**: Use provided mock objects for isolation
3. **Test Edge Cases**: Include tests for boundary conditions and error scenarios
4. **Use Descriptive Test Names**: Test names should clearly describe what is being tested
5. **Follow AAA Pattern**: Arrange, Act, Assert structure for clear test organization

### Integration Testing

1. **Use Test Harness**: Leverage the integration test harness for component testing
2. **Test Real Workflows**: Focus on testing actual user workflows end-to-end
3. **Validate Event Flows**: Ensure events are published and consumed correctly
4. **Test Failure Scenarios**: Include tests for various failure conditions
5. **Clean Up Resources**: Use async context managers for proper cleanup

### Performance Testing

1. **Set Realistic Thresholds**: Define performance thresholds based on requirements
2. **Use Appropriate Load**: Configure load patterns that match expected usage
3. **Monitor System Resources**: Track CPU, memory, and other system metrics
4. **Test Scalability**: Validate performance with increasing system counts
5. **Establish Baselines**: Create performance baselines for regression detection

## Continuous Integration

The testing infrastructure is designed to work with CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run Unit Tests
  run: python -m tests.run_tests --unit --coverage

- name: Run Integration Tests
  run: python -m tests.run_tests --integration

- name: Run Performance Tests
  run: python -m tests.performance.run_performance_tests --quick
```

## Troubleshooting

### Common Issues

1. **Test Timeouts**: Increase timeout values for slow operations
2. **Resource Cleanup**: Ensure proper cleanup in test teardown
3. **Flaky Tests**: Use appropriate wait conditions and retries
4. **Memory Issues**: Monitor memory usage in long-running tests
5. **Coverage Gaps**: Use coverage analysis to identify untested code

### Debug Mode

Enable debug logging for troubleshooting:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Test Isolation

Ensure tests are properly isolated:

- Use fresh mock objects for each test
- Reset singleton instances between tests
- Clean up temporary files and directories
- Disconnect from external resources

## Contributing

When adding new tests:

1. Follow the existing directory structure
2. Use appropriate test markers (`@pytest.mark.unit`, etc.)
3. Include docstrings describing test purpose
4. Add tests for both success and failure scenarios
5. Ensure tests are deterministic and not flaky
6. Update this README if adding new testing patterns

## Performance Benchmarks

Current performance benchmarks (as of implementation):

- **Telemetry Throughput**: Target 50+ ops/sec with <100ms latency
- **Adaptation Latency**: Target <500ms average, <1s P95
- **Error Rate**: Target <5% under normal load, <15% under stress
- **CPU Usage**: Target <80% under normal load, <95% under stress
- **Scalability**: Target 2x+ throughput scaling with 4x system count

These benchmarks are validated by the performance test suite and should be maintained or improved over time.