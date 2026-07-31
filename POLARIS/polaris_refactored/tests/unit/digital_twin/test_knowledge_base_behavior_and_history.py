import pytest
from datetime import datetime, timedelta, timezone

from polaris_refactored.src.infrastructure.data_storage import (
    InMemoryGraphStorageBackend,
    PolarisDataStore,
)
from polaris_refactored.src.digital_twin.knowledge_base import PolarisKnowledgeBase
from polaris_refactored.src.domain.models import (
    SystemState,
    MetricValue,
    HealthStatus,
    AdaptationAction,
    ExecutionResult,
    ExecutionStatus,
)
from polaris_refactored.src.framework.events import TelemetryEvent


@pytest.mark.asyncio
async def test_query_system_behavior_basic():
    backend = InMemoryGraphStorageBackend()
    ds = PolarisDataStore({
        "graph": backend,
        "document": backend,
        "time_series": backend,
    })
    await ds.start()
    kb = PolarisKnowledgeBase(ds)

    system_id = "sys-behavior"
    now = datetime.now(timezone.utc)
    # Insert several states across the last 24h with varying metrics
    states = [
        SystemState(
            system_id=system_id,
            timestamp=now - timedelta(hours=23),
            metrics={
                "cpu": MetricValue(name="cpu", value=0.4),
                "latency": MetricValue(name="latency", value=0.2),
            },
            health_status=HealthStatus.HEALTHY,
        ),
        SystemState(
            system_id=system_id,
            timestamp=now - timedelta(hours=12),
            metrics={
                "cpu": MetricValue(name="cpu", value=0.7),
                "latency": MetricValue(name="latency", value=0.3),
            },
            health_status=HealthStatus.WARNING,
        ),
        SystemState(
            system_id=system_id,
            timestamp=now - timedelta(hours=1),
            metrics={
                "cpu": MetricValue(name="cpu", value=0.9),
                "latency": MetricValue(name="latency", value=0.5),
            },
            health_status=HealthStatus.UNHEALTHY,
        ),
    ]
    for st in states:
        await kb.store_telemetry(TelemetryEvent(system_state=st))

    result = await kb.query_system_behavior(system_id, behavior_type="trend")
    assert result["system_id"] == system_id
    assert result["behavior_type"] == "trend"
    assert result["samples"] >= 3
    summary = result.get("summary", {})
    assert "metric_averages" in summary and "cpu" in summary["metric_averages"]
    # Should have some notes about deltas for cpu/latency
    notes = summary.get("notes", [])
    assert any(n.startswith("cpu_avg_delta") for n in notes) or any(n.startswith("latency_avg_delta") for n in notes)

    await ds.stop()


@pytest.mark.asyncio
async def test_get_adaptation_history_with_execution_results():
    backend = InMemoryGraphStorageBackend()
    ds = PolarisDataStore({
        "graph": backend,
        "document": backend,
        "time_series": backend,
    })
    await ds.start()
    kb = PolarisKnowledgeBase(ds)

    system_id = "sys-history"
    # Create and store an adaptation action
    action = AdaptationAction(
        action_id="act-1",
        action_type="scale_out",
        target_system=system_id,
        parameters={"scale_factor": 2},
        priority=2,
    )
    await kb.store_adaptation_actions([action])

    # Create and store a corresponding execution result
    result = ExecutionResult(
        action_id=action.action_id,
        status=ExecutionStatus.SUCCESS,
        result_data={"nodes_added": 2},
        error_message=None,
        execution_time_ms=1500,
    )
    await kb.store_execution_result(result)

    history = await kb.get_adaptation_history(system_id)
    assert any(h["action_id"] == action.action_id for h in history)
    found = next(h for h in history if h["action_id"] == action.action_id)
    assert found["action_type"] == "scale_out"
    assert found.get("execution_result") is not None
    exec_part = found["execution_result"]
    assert exec_part["status"] == ExecutionStatus.SUCCESS.value
    assert exec_part["result_data"].get("nodes_added") == 2

    await ds.stop()
