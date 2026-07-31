import pytest
import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, Any, List
from unittest.mock import AsyncMock

from polaris_refactored.src.control_reasoning.adaptive_controller import (
    PolarisAdaptiveController,
    AdaptationNeed,
    ReactiveControlStrategy,
    PredictiveControlStrategy,
    LearningControlStrategy,
    ControlStrategy,
)
from polaris_refactored.src.framework.events import TelemetryEvent, AdaptationEvent
from polaris_refactored.src.domain.models import SystemState, MetricValue, HealthStatus, AdaptationAction
from polaris_refactored.src.digital_twin.knowledge_base import PolarisKnowledgeBase
from polaris_refactored.src.digital_twin.world_model import SimulationResult

class MockEventBus:
    def __init__(self):
        self.published = []
        self.publish_calls = 0
        
    async def publish_adaptation_needed(self, event: AdaptationEvent):
        self.publish_calls += 1
        self.published.append(event)


class MockWorldModel:
    async def update_system_state(self, telemetry):
        return None
    async def predict_system_behavior(self, system_id: str, time_horizon: int):
        from polaris_refactored.src.digital_twin.world_model import PredictionResult
        return PredictionResult({"cpu": 0.95}, 0.7)
    async def simulate_adaptation_impact(self, system_id: str, action):
        from polaris_refactored.src.digital_twin.world_model import SimulationResult
        # Favor scale_out by returning better score for lower latency/cpu
        if action.get("action_type") == "scale_out":
            return SimulationResult({"cpu": 0.4, "latency": 0.4}, 0.8)
        return SimulationResult({"cpu": 0.9, "latency": 0.9}, 0.8)
    
    async def predict_system_behavior(self, system_id: str, time_horizon: int):
        return SimulationResult({"cpu": 0.9, "latency": 0.9}, 0.8)


class MockAdaptationPattern:
    def __init__(self, outcomes: Dict[str, Any]):
        self.outcomes = outcomes


class MockKnowledgeBase(PolarisKnowledgeBase):
    """
    A stateful mock that simulates a real knowledge base by storing
    the last known state for each system in an in-memory dictionary.
    """
    def __init__(self):
        self._states: Dict[str, SystemState] = {}
        self.store_telemetry_calls = 0
        self.get_current_state_calls = 0
        self.get_similar_patterns_calls = 0

    async def store_telemetry(self, telemetry: TelemetryEvent):
        """Saves the state from the telemetry event into the internal dictionary."""
        self.store_telemetry_calls += 1
        self._states[telemetry.system_state.system_id] = telemetry.system_state

    async def get_current_state(self, system_id: str) -> Optional[SystemState]:
        """Retrieves the last saved state from the internal dictionary."""
        self.get_current_state_calls += 1
        return self._states.get(system_id)
        
    async def get_similar_patterns(
        self, conditions: Dict[str, Any], similarity_threshold: float
    ) -> List[MockAdaptationPattern]:
        """
        Hardcoded to return a specific pattern for the learning test
        when it sees a high latency condition.
        """
        self.get_similar_patterns_calls += 1
        # This simulates the KB finding a relevant historical pattern
        if conditions.get("latency") == "high":
            return [
                MockAdaptationPattern(
                    outcomes={"action_type": "tune_qos", "parameters": {"qos_level": "high"}}
                )
            ]
        return []


@pytest.mark.asyncio
async def test_assess_and_trigger_reactive_path():
    eb = MockEventBus()
    kb = MockKnowledgeBase()
    ctrl = PolarisAdaptiveController(event_bus=eb, knowledge_base=kb)

    state = SystemState(
        system_id="sys-1",
        timestamp=datetime.now(timezone.utc),
        metrics={
            "cpu": MetricValue(name="cpu", value=0.95),
            "latency": MetricValue(name="latency", value=0.2),
        },
        health_status=HealthStatus.HEALTHY,
    )
    evt = TelemetryEvent(system_state=state)

    await ctrl.process_telemetry(evt)

    # Should publish an adaptation event due to high CPU
    assert len(eb.published) == 1
    pub = eb.published[0]
    assert pub.system_id == "sys-1"
    assert pub.suggested_actions  # non-empty
    # Expect first action to be scale_out from reactive strategy
    assert any(a.action_type == "scale_out" for a in pub.suggested_actions)


@pytest.mark.asyncio
async def test_reactive_strategy_no_action_on_low_metrics():
    """Verify no adaptation is triggered when metrics are within bounds."""
    from polaris_refactored.src.control_reasoning.adaptive_controller import (
        ReactiveControlStrategy, AdaptationNeed
    )
    
    strategy = ReactiveControlStrategy()
    ctx = {"metrics": {
        "cpu": MetricValue(name="cpu", value=0.5),
        "latency": MetricValue(name="latency", value=0.3)
    }}
    need = AdaptationNeed(
        system_id="test-system",
        is_needed=True,
        reason="low metrics",
        urgency=0.8
    )
    actions = await strategy.generate_actions("test-system", ctx, need)
    assert not actions  # No actions should be generated


@pytest.mark.asyncio
async def test_reactive_strategy_multiple_violations():
    """Test handling of multiple metric violations in one check."""
    from polaris_refactored.src.control_reasoning.adaptive_controller import (
        ReactiveControlStrategy, AdaptationNeed
    )
    
    strategy = ReactiveControlStrategy()
    ctx = {"metrics": {
        "cpu": MetricValue(name="cpu", value=0.95),  # Exceeds threshold
        "latency": MetricValue(name="latency", value=0.91)  # Exceeds threshold
    }}
    need = AdaptationNeed(
        system_id="test-system",
        is_needed=True,
        reason="high latency",
        urgency=0.8
    )
    actions = await strategy.generate_actions("test-system", ctx, need)
    
    # Should generate both scale_out and tune_qos actions
    assert len(actions) == 2
    action_types = {a.action_type for a in actions}
    assert "scale_out" in action_types
    assert "tune_qos" in action_types


@pytest.mark.asyncio
async def test_predictive_strategy_selection():
    eb = MockEventBus()
    wm = MockWorldModel()
    kb = MockKnowledgeBase()
    ctrl = PolarisAdaptiveController(event_bus=eb, world_model=wm, knowledge_base=kb)

    state = SystemState(
        system_id="sys-2",
        timestamp=datetime.now(timezone.utc),
        metrics={"cpu": MetricValue(name="cpu", value=0.6)},
        health_status=HealthStatus.HEALTHY,
    )
    evt = TelemetryEvent(system_state=state)

    need = await ctrl.assess_adaptation_need(evt)
    # CPU not high enough, but we'll trigger directly to test planning selection
    need.is_needed = True
    need.reason = "test"
    need.urgency = 0.8

    await ctrl.trigger_adaptation_process(need)

    assert len(eb.published) == 1
    pub = eb.published[0]
    # Predictive strategy should prefer scale_out due to simulation scoring
    assert any(a.action_type == "scale_out" for a in pub.suggested_actions)


@pytest.mark.asyncio
async def test_predictive_strategy_no_viable_actions():
    """Test when simulation finds no viable actions."""
    from unittest.mock import AsyncMock
    from polaris_refactored.src.control_reasoning.adaptive_controller import (
        PredictiveControlStrategy, AdaptationNeed
    )
    from polaris_refactored.src.digital_twin.world_model import SimulationResult
    
    wm = MockWorldModel()
    wm.simulate_adaptation_impact = AsyncMock(return_value=SimulationResult({}, 0.0))
    strategy = PredictiveControlStrategy(wm)
    
    need = AdaptationNeed(
        system_id="test-system",
        is_needed=True,
        reason="high latency",
        urgency=0.8
    )
    actions = await strategy.generate_actions("test-system", {"metrics": {"cpu": MetricValue(name="cpu", value=0.9)}}, need)
    
    # Should return scale_out action as a fallback
    assert len(actions) == 1
    assert actions[0].action_type == "scale_out"
    wm.simulate_adaptation_impact.assert_called()


@pytest.mark.asyncio
async def test_predictive_strategy_simulation_error():
    """Test graceful handling of simulation failures."""
    from unittest.mock import AsyncMock
    from polaris_refactored.src.control_reasoning.adaptive_controller import (
        PredictiveControlStrategy, AdaptationNeed
    )
    
    wm = MockWorldModel()
    wm.simulate_adaptation_impact = AsyncMock(side_effect=Exception("Simulation failed"))
    strategy = PredictiveControlStrategy(wm)
    
    need = AdaptationNeed(
        system_id="test-system",
        is_needed=True,
        reason="simulation error",
        urgency=0.8
    )
    with pytest.raises(Exception, match="Simulation failed"):
        await strategy.generate_actions("test-system", {"metrics": {"cpu": MetricValue(name="cpu", value=0.9)}}, need)


@pytest.mark.asyncio
async def test_learning_strategy_generates_actions():
    eb = MockEventBus()
    kb = MockKnowledgeBase()
    ctrl = PolarisAdaptiveController(event_bus=eb, knowledge_base=kb)

    state = SystemState(
        system_id="sys-3",
        timestamp=datetime.now(timezone.utc),
        metrics={"latency": MetricValue(name="latency", value=0.95)},
        health_status=HealthStatus.HEALTHY,
    )
    evt = TelemetryEvent(system_state=state)

    await ctrl.process_telemetry(evt)

    assert len(eb.published) == 1
    pub = eb.published[0]
    # Should include action suggested by learned pattern (tune_qos)
    assert any(a.action_type == "tune_qos" for a in pub.suggested_actions)


@pytest.mark.asyncio
async def test_learning_strategy_no_similar_patterns():
    """Test when KB returns no similar patterns."""
    from unittest.mock import AsyncMock
    from polaris_refactored.src.control_reasoning.adaptive_controller import (
        LearningControlStrategy, AdaptationNeed
    )
    
    kb = MockKnowledgeBase()
    kb.get_similar_patterns = AsyncMock(return_value=[])
    strategy = LearningControlStrategy(kb)
    
    need = AdaptationNeed(
        system_id="test-system",
        is_needed=True,
        reason="test",
        urgency=0.5
    )
    ctx = {"metrics": {"cpu": MetricValue(name="cpu", value=0.9)}}
    actions = await strategy.generate_actions("test-system", ctx, need)
    
    assert not actions
    kb.get_similar_patterns.assert_called()


@pytest.mark.asyncio
async def test_learning_strategy_invalid_pattern_format():
    """Test handling of malformed pattern data from KB."""
    from unittest.mock import AsyncMock
    from polaris_refactored.src.control_reasoning.adaptive_controller import (
        LearningControlStrategy, AdaptationNeed
    )
    
    class BadPattern:
        def __init__(self):
            self.outcomes = {}  # Empty dict will cause the error in the strategy
    
    kb = MockKnowledgeBase()
    kb.get_similar_patterns = AsyncMock(return_value=[BadPattern()])
    strategy = LearningControlStrategy(kb)
    
    need = AdaptationNeed(
        system_id="test-system",
        is_needed=True,
        reason="test",
        urgency=0.5
    )
    ctx = {"metrics": {"cpu": MetricValue(name="cpu", value=0.9)}}
    
    # Should handle invalid patterns gracefully by returning no actions
    actions = await strategy.generate_actions("test-system", ctx, need)
    assert not actions  # No actions should be generated for invalid patterns


@pytest.mark.asyncio
async def test_controller_no_strategies_available():
    """Test behavior when no control strategies are configured."""
    eb = MockEventBus()
    ctrl = PolarisAdaptiveController(event_bus=eb)
    ctrl._control_strategies = []  # Remove all strategies
    
    state = SystemState(
        system_id="sys-no-strategies",
        timestamp=datetime.now(timezone.utc),
        metrics={"cpu": MetricValue(name="cpu", value=0.95)},
        health_status=HealthStatus.HEALTHY,
    )
    evt = TelemetryEvent(system_state=state)
    
    # The controller should still publish an event even with no strategies
    await ctrl.process_telemetry(evt)
    # Verify adaptation was triggered but with no suggested actions
    assert len(eb.published) == 1
    assert len(eb.published[0].suggested_actions) == 0


@pytest.mark.asyncio
async def test_controller_metrics_update_during_processing():
    """Test handling of metric updates while adaptation is in progress."""
    eb = MockEventBus()
    kb = MockKnowledgeBase()
    
    # Create a slow strategy to simulate processing time
    class SlowStrategy(ControlStrategy):
        async def generate_actions(self, need, context):
            await asyncio.sleep(0.1)  # Simulate processing time
            return [AdaptationAction("scale_out")]
    
    ctrl = PolarisAdaptiveController(
        event_bus=eb,
        knowledge_base=kb,
        control_strategies=[SlowStrategy()]
    )
    
    # First event triggers adaptation
    state1 = SystemState(
        system_id="sys-concurrent",
        timestamp=datetime.now(timezone.utc),
        metrics={"cpu": MetricValue(name="cpu", value=0.95)},
        health_status=HealthStatus.HEALTHY,
    )
    evt1 = TelemetryEvent(system_state=state1)
    
    # Second event with updated metrics before first completes
    state2 = SystemState(
        system_id="sys-concurrent",
        timestamp=datetime.now(timezone.utc),
        metrics={"cpu": MetricValue(name="cpu", value=0.4)},
        health_status=HealthStatus.HEALTHY,
    )
    evt2 = TelemetryEvent(system_state=state2)
    
    # Process both events nearly simultaneously
    task1 = asyncio.create_task(ctrl.process_telemetry(evt1))
    task2 = asyncio.create_task(ctrl.process_telemetry(evt2))
    await asyncio.gather(task1, task2)
    
    # Verify only one adaptation was triggered (deduplicated)
    assert len(eb.published) == 1
