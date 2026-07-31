import asyncio
import pytest

from polaris_refactored.src.adapters.execution_adapter import (
    ValidationStage,
    PreConditionCheckStage,
    ActionExecutionStage,
    PostExecutionVerificationStage,
)
from polaris_refactored.src.domain.models import (
    AdaptationAction,
    ExecutionResult,
    ExecutionStatus,
    SystemState,
    MetricValue,
    HealthStatus,
)
from polaris_refactored.src.domain.interfaces import ManagedSystemConnector
from datetime import datetime, timezone


class FakeConnector(ManagedSystemConnector):
    def __init__(self, supported=None, state_metrics=None, should_timeout=False):
        self._supported = supported or ["TEST_ACTION"]
        self._should_timeout = should_timeout
        mv = state_metrics or {"dummy": MetricValue(name="dummy", value=1)}
        self._state = SystemState(
            system_id="system-A",
            timestamp=datetime.now(timezone.utc),
            metrics=mv,
            health_status=HealthStatus.HEALTHY,
        )

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> bool:
        return True

    async def get_system_id(self) -> str:
        return "system-A"

    async def collect_metrics(self):
        return self._state.metrics

    async def get_system_state(self) -> SystemState:
        return self._state

    async def execute_action(self, action: AdaptationAction) -> ExecutionResult:
        if self._should_timeout:
            # Simulate long running to trigger timeout in stage
            await asyncio.sleep(2)
        return ExecutionResult(
            action_id=action.action_id,
            status=ExecutionStatus.SUCCESS,
            result_data={"ok": True},
        )

    async def validate_action(self, action: AdaptationAction) -> bool:
        return True

    async def get_supported_actions(self):
        return list(self._supported)


@pytest.mark.asyncio
async def test_validation_stage_success():
    connector = FakeConnector(supported=["TEST_ACTION"]) 
    stage = ValidationStage()
    action = AdaptationAction(
        action_id="a1",
        action_type="TEST_ACTION",
        target_system="system-A",
        parameters={},
    )
    context = {"connector": connector}

    out = await stage.execute(action, context)

    assert out["stage_results"]["ValidationStage"] == "success"


@pytest.mark.asyncio
async def test_precondition_stage_fetches_state():
    connector = FakeConnector()
    stage = PreConditionCheckStage()
    action = AdaptationAction(
        action_id="a2",
        action_type="TEST_ACTION",
        target_system="system-A",
        parameters={},
    )
    context = {"connector": connector}

    out = await stage.execute(action, context)

    assert out["stage_results"]["PreConditionCheckStage"] == "success"
    assert "pre_state" in out


@pytest.mark.asyncio
async def test_action_execution_stage_success():
    connector = FakeConnector()
    stage = ActionExecutionStage(timeout_seconds=1)
    action = AdaptationAction(
        action_id="a3",
        action_type="TEST_ACTION",
        target_system="system-A",
        parameters={},
    )
    context = {"connector": connector}

    out = await stage.execute(action, context)

    assert "execution_result" in out
    assert out["execution_result"].status == ExecutionStatus.SUCCESS


@pytest.mark.asyncio
async def test_action_execution_stage_timeout():
    connector = FakeConnector(should_timeout=True)
    stage = ActionExecutionStage(timeout_seconds=0)  # immediate timeout
    action = AdaptationAction(
        action_id="a4",
        action_type="TEST_ACTION",
        target_system="system-A",
        parameters={},
    )
    context = {"connector": connector}

    out = await stage.execute(action, context)

    assert out["execution_result"].status in (ExecutionStatus.TIMEOUT, ExecutionStatus.FAILED)


@pytest.mark.asyncio
async def test_post_verification_stage_skips_on_failure():
    connector = FakeConnector()
    stage = PostExecutionVerificationStage()
    action = AdaptationAction(
        action_id="a5",
        action_type="TEST_ACTION",
        target_system="system-A",
        parameters={},
    )
    # No execution_result in context (simulate previous failure)
    context = {"connector": connector}

    out = await stage.execute(action, context)

    assert out["stage_results"]["PostExecutionVerificationStage"] == "skipped"
