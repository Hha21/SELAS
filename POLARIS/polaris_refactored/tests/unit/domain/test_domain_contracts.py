import pytest
import asyncio
from datetime import datetime, timezone

from polaris_refactored.src.domain.interfaces import ManagedSystemConnector, AdaptationCommand, EventHandler
from polaris_refactored.src.domain.models import (
    MetricValue,
    SystemState,
    AdaptationAction,
    ExecutionResult,
    ExecutionStatus,
    HealthStatus,
    SystemDependency,
    LearnedPattern,
)


def test_metric_value_defaults_timestamp_and_tags():
    mv = MetricValue(name="cpu", value=0.5, unit="pct")
    assert mv.timestamp is not None
    assert isinstance(mv.tags, dict) and mv.tags == {}


def test_adaptation_action_defaults_and_uuid_generation():
    a = AdaptationAction(action_id="", action_type="scale", target_system="svc", parameters={})
    assert a.action_id and isinstance(a.action_id, str)
    assert a.created_at is not None


def test_system_dependency_strength_bounds():
    SystemDependency(source_system="a", target_system="b", dependency_type="d", strength=0.0)
    SystemDependency(source_system="a", target_system="b", dependency_type="d", strength=1.0)
    with pytest.raises(ValueError):
        SystemDependency(source_system="a", target_system="b", dependency_type="d", strength=-0.1)
    with pytest.raises(ValueError):
        SystemDependency(source_system="a", target_system="b", dependency_type="d", strength=1.1)


def test_learned_pattern_confidence_bounds():
    LearnedPattern(
        pattern_id="p",
        pattern_type="t",
        conditions={},
        outcomes={},
        confidence=0.0,
        learned_at=datetime.now(timezone.utc),
    )
    LearnedPattern(
        pattern_id="p",
        pattern_type="t",
        conditions={},
        outcomes={},
        confidence=1.0,
        learned_at=datetime.now(timezone.utc),
    )
    with pytest.raises(ValueError):
        LearnedPattern(
            pattern_id="p",
            pattern_type="t",
            conditions={},
            outcomes={},
            confidence=-0.01,
            learned_at=datetime.now(timezone.utc),
        )
    with pytest.raises(ValueError):
        LearnedPattern(
            pattern_id="p",
            pattern_type="t",
            conditions={},
            outcomes={},
            confidence=1.1,
            learned_at=datetime.now(timezone.utc),
        )


@pytest.mark.asyncio
async def test_managed_system_connector_contract_via_minimal_impl():
    class MiniConnector(ManagedSystemConnector):
        async def connect(self) -> bool:
            return True
        async def disconnect(self) -> bool:
            return True
        async def get_system_id(self) -> str:
            return "svc"
        async def collect_metrics(self):
            return {"cpu": MetricValue(name="cpu", value=1)}
        async def get_system_state(self) -> SystemState:
            return SystemState(system_id="svc", timestamp=datetime.now(timezone.utc), metrics={}, health_status=HealthStatus.HEALTHY)
        async def execute_action(self, action: AdaptationAction) -> ExecutionResult:
            return ExecutionResult(action_id=action.action_id, status=ExecutionStatus.SUCCESS, result_data={})
        async def validate_action(self, action: AdaptationAction) -> bool:
            return True
        async def get_supported_actions(self):
            return ["scale"]

    c = MiniConnector()
    assert await c.connect() is True
    assert await c.get_system_id() == "svc"
    res = await c.execute_action(AdaptationAction(action_id="a", action_type="scale", target_system="svc", parameters={}))
    assert res.status == ExecutionStatus.SUCCESS


@pytest.mark.asyncio
async def test_event_handler_contract():
    class SimpleHandler(EventHandler):
        def __init__(self):
            self.handled = []
        async def handle(self, event: object) -> None:
            self.handled.append(event)
        def can_handle(self, event: object) -> bool:
            return True

    h = SimpleHandler()
    assert h.can_handle(object()) is True
    await h.handle({"x": 1})
    assert h.handled == [{"x": 1}]
