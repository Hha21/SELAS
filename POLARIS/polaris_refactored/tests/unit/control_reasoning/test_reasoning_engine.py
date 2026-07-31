import pytest
from datetime import datetime, timedelta, timezone

from polaris_refactored.src.control_reasoning.reasoning_engine import (
    PolarisReasoningEngine,
    ReasoningContext,
    StatisticalReasoningStrategy,
    CausalReasoningStrategy,
    ExperienceBasedReasoningStrategy,
)
from polaris_refactored.src.domain.models import MetricValue, HealthStatus, SystemState


class MockKB:
    def __init__(self):
        self._states = {}
        self._deps = {"sys-A": {"neighbors": ["sys-B"]}}
    async def get_historical_states(self, system_id, start, end):
        # create simple historical series
        return [
            SystemState(
                system_id=system_id,
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=10*i),
                metrics={"cpu": MetricValue(name="cpu", value=v)},
                health_status=HealthStatus.HEALTHY,
            )
            for i, v in enumerate([0.2, 0.3, 0.4, 0.5])
        ]
    async def get_dependency_chain(self, system_id: str, max_depth: int = 2):
        return self._deps.get(system_id, {})
    async def get_current_state(self, system_id: str):
        return self._states.get(system_id)
    async def get_similar_patterns(self, conditions, similarity_threshold: float = 0.6):
        class P:
            def __init__(self):
                self.pattern_id = "pat-1"
                self.conditions = {"cpu": "high"}
                self.outcomes = {"action_type": "scale_out", "parameters": {"scale_factor": 2}}
                self.confidence = 0.8
        if conditions:
            return [P()]
        return []


@pytest.mark.asyncio
async def test_statistical_reasoning_detects_anomaly():
    kb = MockKB()
    strat = StatisticalReasoningStrategy(knowledge_base=kb)
    ctx = ReasoningContext(
        system_id="sys-A",
        current_state={"metrics": {"cpu": MetricValue(name="cpu", value=1.0)}},
    )
    res = await strat.reason(ctx)
    assert any(i.get("type") == "statistical_anomaly" for i in res.insights)
    assert res.confidence >= 0.6


@pytest.mark.asyncio
async def test_causal_reasoning_uses_dependency_graph():
    kb = MockKB()
    strat = CausalReasoningStrategy(knowledge_base=kb)
    ctx = ReasoningContext(
        system_id="sys-A",
        current_state={"metrics": {"latency": MetricValue(name="latency", value=0.95)}},
    )
    res = await strat.reason(ctx)
    assert any(i.get("type") == "causal_link" for i in res.insights)


@pytest.mark.asyncio
async def test_experience_based_recommends_actions():
    kb = MockKB()
    strat = ExperienceBasedReasoningStrategy(knowledge_base=kb)
    ctx = ReasoningContext(
        system_id="sys-A",
        current_state={"metrics": {"cpu": MetricValue(name="cpu", value=0.95)}},
    )
    res = await strat.reason(ctx)
    assert res.recommendations
    assert any(r.get("action_type") == "scale_out" for r in res.recommendations)


@pytest.mark.asyncio
async def test_engine_fuses_results():
    kb = MockKB()
    engine = PolarisReasoningEngine(knowledge_base=kb)
    ctx = ReasoningContext(
        system_id="sys-A",
        current_state={"metrics": {"cpu": MetricValue(name="cpu", value=0.95)}},
    )
    res = await engine.reason(ctx)
    assert res.insights
    # Confidence should be > 0 due to fusion of strategies
    assert res.confidence > 0.0
