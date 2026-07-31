import asyncio
import pytest

from polaris_refactored.src.adapters.execution_adapter import (
    ActionExecutionPipeline,
    ValidationStage,
    PreConditionCheckStage,
    ActionExecutionStage,
    PostExecutionVerificationStage,
)
from polaris_refactored.src.domain.models import AdaptationAction, ExecutionStatus, SystemState, MetricValue, HealthStatus, ExecutionResult
from polaris_refactored.src.domain.interfaces import ManagedSystemConnector
from datetime import datetime, timezone


class SimpleConnector(ManagedSystemConnector):
    def __init__(self, should_fail=False):
        self._should_fail = should_fail
        self._state = SystemState(
            system_id="system-A",
            timestamp=datetime.now(timezone.utc),
            metrics={"dummy": MetricValue(name="dummy", value=1)},
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
        if self._should_fail:
            raise RuntimeError("Execution error")
        return ExecutionResult(
            action_id=action.action_id,
            status=ExecutionStatus.SUCCESS,
            result_data={"ran": True},
        )

    async def validate_action(self, action: AdaptationAction) -> bool:
        return True

    async def get_supported_actions(self):
        return ["TEST_ACTION"]


@pytest.mark.asyncio
async def test_pipeline_success_path():
    pipeline = ActionExecutionPipeline(
        stages=[
            ValidationStage(),
            PreConditionCheckStage(),
            ActionExecutionStage(timeout_seconds=1),
            PostExecutionVerificationStage(),
        ]
    )

    action = AdaptationAction(
        action_id="p1",
        action_type="TEST_ACTION",
        target_system="system-A",
        parameters={},
    )
    connector = SimpleConnector()

    result = await pipeline.execute(action, initial_context={"connector": connector})

    assert result.status == ExecutionStatus.SUCCESS


@pytest.mark.asyncio
async def test_pipeline_stage_failure_maps_to_failed_result():
    pipeline = ActionExecutionPipeline(
        stages=[
            ValidationStage(),
            PreConditionCheckStage(),
            ActionExecutionStage(timeout_seconds=1),
            PostExecutionVerificationStage(),
        ]
    )

    action = AdaptationAction(
        action_id="p2",
        action_type="TEST_ACTION",
        target_system="system-A",
        parameters={},
    )
    # Force failure in execution stage via connector
    bad_connector = SimpleConnector(should_fail=True)

    result = await pipeline.execute(action, initial_context={"connector": bad_connector})

    assert result.status == ExecutionStatus.FAILED or result.status == ExecutionStatus.PARTIAL
    assert result.error_message is not None
