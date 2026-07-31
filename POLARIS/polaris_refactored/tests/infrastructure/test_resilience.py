"""
Tests for resilience patterns.
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, Mock

from polaris_refactored.src.infrastructure.resilience import (
    CircuitBreaker, CircuitBreakerConfig, CircuitBreakerState, CircuitBreakerError,
    RetryPolicy, RetryConfig,
    Bulkhead, BulkheadConfig, BulkheadError,
    ResilienceManager
)
from polaris_refactored.src.infrastructure.exceptions import PolarisException


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    @pytest.fixture
    def circuit_breaker(self):
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=1.0,
            success_threshold=2,
            timeout=0.5
        )
        return CircuitBreaker("test_service", config)
    
    @pytest.mark.asyncio
    async def test_successful_operation(self, circuit_breaker):
        """Test successful operation keeps circuit closed."""
        async def success_func():
            return "success"
        
        result = await circuit_breaker.call(success_func)
        assert result == "success"
        assert circuit_breaker.state == CircuitBreakerState.CLOSED
        assert circuit_breaker.failure_count == 0
    
    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self, circuit_breaker):
        """Test circuit opens after threshold failures."""
        async def failing_func():
            raise Exception("Service unavailable")
        
        # First 2 failures should keep circuit closed
        for i in range(2):
            with pytest.raises(Exception):
                await circuit_breaker.call(failing_func)
            assert circuit_breaker.state == CircuitBreakerState.CLOSED
        
        # Third failure should open circuit
        with pytest.raises(Exception):
            await circuit_breaker.call(failing_func)
        assert circuit_breaker.state == CircuitBreakerState.OPEN
    
    @pytest.mark.asyncio
    async def test_circuit_rejects_when_open(self, circuit_breaker):
        """Test circuit rejects calls when open."""
        async def failing_func():
            raise Exception("Service unavailable")
        
        # Trigger circuit to open
        for _ in range(3):
            with pytest.raises(Exception):
                await circuit_breaker.call(failing_func)
        
        assert circuit_breaker.state == CircuitBreakerState.OPEN
        
        # Should reject with CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            await circuit_breaker.call(failing_func)
    
    @pytest.mark.asyncio
    async def test_circuit_half_open_recovery(self, circuit_breaker):
        """Test circuit recovery through half-open state."""
        async def failing_func():
            raise Exception("Service unavailable")
        
        async def success_func():
            return "recovered"
        
        # Open the circuit
        for _ in range(3):
            with pytest.raises(Exception):
                await circuit_breaker.call(failing_func)
        
        assert circuit_breaker.state == CircuitBreakerState.OPEN
        
        # Wait for recovery timeout
        await asyncio.sleep(1.1)
        
        # First call should move to half-open
        result = await circuit_breaker.call(success_func)
        assert result == "recovered"
        assert circuit_breaker.state == CircuitBreakerState.HALF_OPEN
        
        # Second success should close circuit
        result = await circuit_breaker.call(success_func)
        assert result == "recovered"
        assert circuit_breaker.state == CircuitBreakerState.CLOSED
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self, circuit_breaker):
        """Test operation timeout handling."""
        async def slow_func():
            await asyncio.sleep(1.0)  # Longer than timeout
            return "too_slow"
        
        with pytest.raises(PolarisException) as exc_info:
            await circuit_breaker.call(slow_func)
        
        assert "timed out" in str(exc_info.value)
        assert circuit_breaker.failure_count == 1
    
    def test_get_state(self, circuit_breaker):
        """Test state reporting."""
        state = circuit_breaker.get_state()
        
        assert state["name"] == "test_service"
        assert state["state"] == "closed"
        assert state["failure_count"] == 0
        assert state["success_count"] == 0


class TestRetryPolicy:
    """Test retry policy functionality."""
    
    @pytest.fixture
    def retry_policy(self):
        config = RetryConfig(
            max_attempts=3,
            base_delay=0.1,
            max_delay=1.0,
            exponential_base=2.0,
            jitter=False  # Disable for predictable testing
        )
        return RetryPolicy(config)
    
    @pytest.mark.asyncio
    async def test_successful_operation_no_retry(self, retry_policy):
        """Test successful operation doesn't retry."""
        call_count = 0
        
        async def success_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await retry_policy.execute(success_func, "test_op")
        assert result == "success"
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_retry_on_failure(self, retry_policy):
        """Test retry behavior on failures."""
        call_count = 0
        
        async def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception(f"Failure {call_count}")
            return "success"
        
        start_time = asyncio.get_event_loop().time()
        result = await retry_policy.execute(failing_then_success, "test_op")
        end_time = asyncio.get_event_loop().time()
        
        assert result == "success"
        assert call_count == 3
        # Should have delays: 0.1 + 0.2 = 0.3s minimum
        assert end_time - start_time >= 0.3
    
    @pytest.mark.asyncio
    async def test_retry_exhaustion(self, retry_policy):
        """Test behavior when all retries are exhausted."""
        call_count = 0
        
        async def always_failing():
            nonlocal call_count
            call_count += 1
            raise Exception(f"Failure {call_count}")
        
        with pytest.raises(PolarisException) as exc_info:
            await retry_policy.execute(always_failing, "test_op")
        
        assert "failed after 3 attempts" in str(exc_info.value)
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_non_retryable_exception(self):
        """Test non-retryable exceptions are not retried."""
        config = RetryConfig(retryable_exceptions=(ValueError,))
        retry_policy = RetryPolicy(config)
        
        call_count = 0
        
        async def non_retryable_failure():
            nonlocal call_count
            call_count += 1
            raise TypeError("Not retryable")
        
        with pytest.raises(TypeError):
            await retry_policy.execute(non_retryable_failure, "test_op")
        
        assert call_count == 1  # Should not retry


class TestBulkhead:
    """Test bulkhead functionality."""
    
    @pytest.fixture
    def bulkhead(self):
        config = BulkheadConfig(
            max_concurrent=2,
            queue_size=3,
            timeout=0.5
        )
        return Bulkhead("test_resource", config)
    
    @pytest.mark.asyncio
    async def test_concurrent_execution(self, bulkhead):
        """Test concurrent execution within limits."""
        results = []
        
        async def test_operation(value):
            await asyncio.sleep(0.1)
            results.append(value)
            return value
        
        # Start 2 concurrent operations (at limit)
        tasks = [
            bulkhead.execute(lambda v=i: test_operation(v), f"op_{i}")
            for i in range(2)
        ]
        
        await asyncio.gather(*tasks)
        assert len(results) == 2
        assert set(results) == {0, 1}
    
    @pytest.mark.asyncio
    async def test_queue_management(self, bulkhead):
        """Test queue management for excess operations."""
        execution_order = []
        
        async def slow_operation(value):
            execution_order.append(f"start_{value}")
            await asyncio.sleep(0.2)
            execution_order.append(f"end_{value}")
            return value
        
        # Start operations that will fill capacity and queue
        tasks = [
            bulkhead.execute(lambda v=i: slow_operation(v), f"op_{i}")
            for i in range(4)  # 2 concurrent + 2 queued
        ]
        
        results = await asyncio.gather(*tasks)
        assert len(results) == 4
        assert set(results) == {0, 1, 2, 3}
    
    @pytest.mark.asyncio
    async def test_queue_overflow_rejection(self, bulkhead):
        """Test rejection when queue is full."""
        async def long_operation():
            await asyncio.sleep(1.0)
            return "done"
        
        # Fill capacity and queue
        tasks = []
        for i in range(5):  # 2 concurrent + 3 queued
            task = asyncio.create_task(bulkhead.execute(long_operation, f"op_{i}"))
            tasks.append(task)

        # Allow the event loop a moment to start the tasks and fill the bulkhead
        await asyncio.sleep(0.5)

        # This should be rejected
        with pytest.raises(BulkheadError) as exc_info:
            await bulkhead.execute(long_operation, "overflow_op")
        
        assert "Queue full" in str(exc_info.value)
        
        # Cancel running tasks to clean up
        for task in tasks:
            task.cancel()
        
        # Wait a bit and suppress cancellation errors
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except:
            pass
    
    @pytest.mark.asyncio
    async def test_timeout_acquisition(self, bulkhead):
        """Test timeout when waiting for resource."""
        async def blocking_operation():
            await asyncio.sleep(1.0)
            return "done"
        
        # Fill capacity
        tasks = [
            asyncio.create_task(bulkhead.execute(blocking_operation, f"blocking_{i}"))
            for i in range(2)
        ]
        
        await asyncio.sleep(0.5)

        # This should timeout waiting for semaphore
        with pytest.raises(BulkheadError) as exc_info:
            await bulkhead.execute(blocking_operation, "timeout_op")
        
        assert "Timeout waiting" in str(exc_info.value)
        
        # Cancel running tasks
        for task in tasks:
            task.cancel()
        
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except:
            pass
    
    def test_get_stats(self, bulkhead):
        """Test statistics reporting."""
        stats = bulkhead.get_stats()
        
        assert stats["name"] == "test_resource"
        assert stats["max_concurrent"] == 2
        assert stats["active_operations"] == 0
        assert stats["queue_size"] == 0
        assert stats["utilization"] == 0.0


class TestResilienceManager:
    """Test resilience manager functionality."""
    
    @pytest.fixture
    def manager(self):
        return ResilienceManager()
    
    def test_circuit_breaker_management(self, manager):
        """Test circuit breaker creation and retrieval."""
        cb1 = manager.get_circuit_breaker("service1")
        cb2 = manager.get_circuit_breaker("service1")  # Should return same instance
        cb3 = manager.get_circuit_breaker("service2")  # Should create new instance
        
        assert cb1 is cb2
        assert cb1 is not cb3
        assert cb1.name == "service1"
        assert cb3.name == "service2"
    
    def test_bulkhead_management(self, manager):
        """Test bulkhead creation and retrieval."""
        bh1 = manager.get_bulkhead("resource1")
        bh2 = manager.get_bulkhead("resource1")  # Should return same instance
        bh3 = manager.get_bulkhead("resource2")  # Should create new instance
        
        assert bh1 is bh2
        assert bh1 is not bh3
        assert bh1.name == "resource1"
        assert bh3.name == "resource2"
    
    def test_retry_policy_management(self, manager):
        """Test retry policy creation."""
        rp1 = manager.get_retry_policy()  # Default
        rp2 = manager.get_retry_policy()  # Should return same default instance
        
        config = RetryConfig(max_attempts=5)
        rp3 = manager.get_retry_policy(config)  # Should create new instance
        
        assert rp1 is rp2
        assert rp1 is not rp3
    
    @pytest.mark.asyncio
    async def test_execute_with_resilience(self, manager):
        """Test combined resilience patterns."""
        call_count = 0
        
        async def test_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Transient failure")
            return "success"
        
        result = await manager.execute_with_resilience(
            test_operation,
            "test_op",
            circuit_breaker_name="test_cb",
            bulkhead_name="test_bh",
            retry_config=RetryConfig(max_attempts=3, base_delay=0.01)
        )
        
        assert result == "success"
        assert call_count == 2  # Should have retried once
    
    def test_get_all_stats(self, manager):
        """Test statistics collection."""
        # Create some components
        manager.get_circuit_breaker("cb1")
        manager.get_bulkhead("bh1")
        
        stats = manager.get_all_stats()
        
        assert "circuit_breakers" in stats
        assert "bulkheads" in stats
        assert "cb1" in stats["circuit_breakers"]
        assert "bh1" in stats["bulkheads"]