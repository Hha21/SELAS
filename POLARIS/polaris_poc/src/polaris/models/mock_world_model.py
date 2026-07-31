"""
Mock World Model for testing and development.
"""
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from .digital_twin_events import KnowledgeEvent, CalibrationEvent
from .world_model import (QueryRequest, QueryResponse, SimulationRequest, SimulationResponse,
                          DiagnosisRequest, DiagnosisResponse, WorldModel, WorldModelFactory)


# Mock World Model for testing and development
class MockWorldModel(WorldModel):
    """
    Mock World Model implementation for testing and development.

    This implementation provides simple responses without actual AI/ML
    processing, useful for testing the Digital Twin infrastructure.
    """

    async def initialize(self) -> None:
        """Initialize the mock model."""
        self.logger.info("Initializing MockWorldModel")
        self._set_initialized(True)

    async def shutdown(self) -> None:
        """Shutdown the mock model."""
        self.logger.info("Shutting down MockWorldModel")
        self._set_initialized(False)

    async def update_state(self, event: KnowledgeEvent) -> None:
        """Mock state update."""
        self.logger.debug(
            f"Mock state update: {event.event_type} from {event.source}")

    async def calibrate(self, event: CalibrationEvent) -> None:
        """Mock calibration."""
        accuracy = event.calculate_accuracy_score()
        self.logger.debug(f"Mock calibration: accuracy={accuracy:.2f}")

    async def query_state(self, request: QueryRequest) -> QueryResponse:
        """Mock query response."""
        return QueryResponse(
            query_id=request.query_id,
            success=True,
            result=f"Mock response for {request.query_type} query: {request.query_content}",
            confidence=0.8,
            explanation="This is a mock response for testing purposes"
        )

    async def simulate(self, request: SimulationRequest) -> SimulationResponse:
        """Mock simulation response."""
        return SimulationResponse(
            simulation_id=request.simulation_id,
            success=True,
            future_states=[{"time": "+30min", "cpu": 75.0},
                           {"time": "+60min", "cpu": 70.0}],
            confidence=0.7,
            uncertainty_lower=0.6,
            uncertainty_upper=0.8,
            explanation="Mock simulation showing gradual CPU decrease"
        )

    async def diagnose(self, request: DiagnosisRequest) -> DiagnosisResponse:
        """Mock diagnosis response."""
        return DiagnosisResponse(
            diagnosis_id=request.diagnosis_id,
            success=True,
            hypotheses=["High CPU usage", "Memory leak", "Network congestion"],
            causal_chain="Resource exhaustion -> Performance degradation -> User impact",
            confidence=0.75,
            explanation="Mock diagnosis identifying resource-related issues",
            supporting_evidence=["CPU metrics",
                                 "Memory trends", "Response times"]
        )

    async def get_health_status(self) -> Dict[str, Any]:
        """Mock health status."""
        return {
            "status": "healthy" if self.is_initialized else "not_initialized",
            "model_type": "mock",
            "last_check": datetime.now(timezone.utc).isoformat(),
            "metrics": {"queries_processed": 0, "accuracy": 0.8}
        }

    async def reload_model(self) -> bool:
        """Mock model reload."""
        self.logger.info("Mock model reload")
        return True


# Enhanced Mock World Model with better testing support
class TestableWorldModel(MockWorldModel):
    __test__ = False  # prevent pytest collection
    """
    Enhanced Mock World Model with additional testing capabilities.
    
    This implementation extends the basic MockWorldModel with features
    specifically designed for testing and validation purposes.
    """

    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """Initialize the testable mock model."""
        super().__init__(config, logger)
        self._operation_history = []
        self._error_simulation = {}
        self._response_delays = {}

    def set_error_simulation(self, operation: str, error_message: str) -> None:
        """Configure the model to simulate errors for testing.

        Args:
            operation: Operation name to simulate error for
            error_message: Error message to raise
        """
        self._error_simulation[operation] = error_message

    def set_response_delay(self, operation: str, delay_seconds: float) -> None:
        """Configure response delays for testing.

        Args:
            operation: Operation name to add delay to
            delay_seconds: Delay in seconds
        """
        self._response_delays[operation] = delay_seconds

    def get_operation_history(self) -> list:
        """Get history of operations performed on this model.

        Returns:
            List of operation records
        """
        return self._operation_history.copy()

    def clear_operation_history(self) -> None:
        """Clear the operation history."""
        self._operation_history.clear()

    async def _simulate_operation(self, operation_name: str) -> None:
        """Simulate operation with potential errors and delays."""
        # Record operation
        self._operation_history.append({
            "operation": operation_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # Simulate error if configured
        if operation_name in self._error_simulation:
            raise WorldModelOperationError(
                self._error_simulation[operation_name])

        # Simulate delay if configured
        if operation_name in self._response_delays:
            await asyncio.sleep(self._response_delays[operation_name])

    async def update_state(self, event: KnowledgeEvent) -> None:
        """Mock state update with testing features."""
        await self._simulate_operation("update_state")
        await super().update_state(event)

    async def calibrate(self, event: CalibrationEvent) -> None:
        """Mock calibration with testing features."""
        await self._simulate_operation("calibrate")
        await super().calibrate(event)

    async def query_state(self, request: QueryRequest) -> QueryResponse:
        """Mock query with testing features."""
        await self._simulate_operation("query_state")
        return await super().query_state(request)

    async def simulate(self, request: SimulationRequest) -> SimulationResponse:
        """Mock simulation with testing features."""
        await self._simulate_operation("simulate")
        return await super().simulate(request)

    async def diagnose(self, request: DiagnosisRequest) -> DiagnosisResponse:
        """Mock diagnosis with testing features."""
        await self._simulate_operation("diagnose")
        return await super().diagnose(request)

    async def get_health_status(self) -> Dict[str, Any]:
        """Mock health status with testing features."""
        await self._simulate_operation("get_health_status")
        status = await super().get_health_status()
        status["operation_count"] = len(self._operation_history)
        status["configured_errors"] = list(self._error_simulation.keys())
        status["configured_delays"] = list(self._response_delays.keys())
        return status

    async def reload_model(self) -> bool:
        """Mock model reload with testing features."""
        await self._simulate_operation("reload_model")
        return await super().reload_model()


# Register the models on import
WorldModelFactory.register("mock", MockWorldModel)
WorldModelFactory.register("testable", TestableWorldModel)
