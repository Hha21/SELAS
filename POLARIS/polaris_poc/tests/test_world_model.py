"""
Unit tests for World Model interface and factory.

Tests the abstract interface, factory pattern, and mock implementation.
"""

import pytest
import pytest_asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock

# Add parent directory to path to import from polaris
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from polaris.models.world_model import (
    WorldModel, WorldModelFactory,
    WorldModelError, WorldModelInitializationError, WorldModelOperationError,
    QueryRequest, QueryResponse, SimulationRequest, SimulationResponse,
    DiagnosisRequest, DiagnosisResponse
)
from polaris.models.mock_world_model import MockWorldModel
from polaris.models.digital_twin_events import KnowledgeEvent, CalibrationEvent


class TestWorldModelInterface:
    """Test cases for World Model abstract interface."""
    
    def test_world_model_is_abstract(self):
        """Test that WorldModel cannot be instantiated directly."""
        with pytest.raises(TypeError):
            WorldModel({})
    
    def test_request_response_objects(self):
        """Test request and response object creation."""
        # Test QueryRequest
        query_req = QueryRequest(
            query_id="q1",
            query_type="current_state",
            query_content="What is the CPU usage?",
            parameters={"system": "prod"}
        )
        assert query_req.query_id == "q1"
        assert query_req.query_type == "current_state"
        assert query_req.parameters["system"] == "prod"
        assert query_req.timestamp is not None
        
        # Test QueryResponse
        query_resp = QueryResponse(
            query_id="q1",
            success=True,
            result="CPU usage is 75%",
            confidence=0.9,
            explanation="Based on latest telemetry"
        )
        assert query_resp.query_id == "q1"
        assert query_resp.success is True
        assert query_resp.confidence == 0.9
        assert query_resp.timestamp is not None
        
        # Test SimulationRequest
        sim_req = SimulationRequest(
            simulation_id="s1",
            simulation_type="forecast",
            actions=[{"type": "scale_up", "count": 2}],
            horizon_minutes=30
        )
        assert sim_req.simulation_id == "s1"
        assert sim_req.simulation_type == "forecast"
        assert len(sim_req.actions) == 1
        assert sim_req.horizon_minutes == 30
        
        # Test SimulationResponse
        sim_resp = SimulationResponse(
            simulation_id="s1",
            success=True,
            future_states=[{"time": "+15min", "cpu": 60}],
            confidence=0.8,
            uncertainty_lower=0.7,
            uncertainty_upper=0.9,
            explanation="Forecast shows CPU decrease"
        )
        assert sim_resp.simulation_id == "s1"
        assert len(sim_resp.future_states) == 1
        assert sim_resp.uncertainty_lower == 0.7
        
        # Test DiagnosisRequest
        diag_req = DiagnosisRequest(
            diagnosis_id="d1",
            anomaly_description="High response times",
            context={"severity": "high"}
        )
        assert diag_req.diagnosis_id == "d1"
        assert diag_req.anomaly_description == "High response times"
        assert diag_req.context["severity"] == "high"
        
        # Test DiagnosisResponse
        diag_resp = DiagnosisResponse(
            diagnosis_id="d1",
            success=True,
            hypotheses=["Database overload", "Network issues"],
            causal_chain="Load increase -> DB bottleneck -> Slow responses",
            confidence=0.85,
            explanation="Analysis points to database issues"
        )
        assert diag_resp.diagnosis_id == "d1"
        assert len(diag_resp.hypotheses) == 2
        assert "DB bottleneck" in diag_resp.causal_chain


class TestWorldModelFactory:
    """Test cases for WorldModelFactory."""
    
    def setup_method(self):
        """Clear registry before each test."""
        WorldModelFactory.clear_registry()
    
    def teardown_method(self):
        """Clean up after each test."""
        WorldModelFactory.clear_registry()
        # Re-register mock model for other tests
        WorldModelFactory.register("mock", MockWorldModel)
    
    def test_factory_registration(self):
        """Test model registration in factory."""
        # Test registration
        WorldModelFactory.register("test", MockWorldModel)
        assert WorldModelFactory.is_registered("test")
        assert WorldModelFactory.is_registered("TEST")  # case insensitive
        assert "test" in WorldModelFactory.get_registered_types()
        
        # Test invalid registration
        class NotAWorldModel:
            pass
        
        with pytest.raises(ValueError) as exc_info:
            WorldModelFactory.register("invalid", NotAWorldModel)
        assert "must be a subclass of WorldModel" in str(exc_info.value)
    
    def test_factory_model_creation(self):
        """Test model creation through factory."""
        WorldModelFactory.register("mock", MockWorldModel)
        
        # Test successful creation
        config = {"test": "value"}
        model = WorldModelFactory.create_model("mock", config)
        assert isinstance(model, MockWorldModel)
        assert model.config == config
        
        # Test case insensitive creation
        model2 = WorldModelFactory.create_model("MOCK", config)
        assert isinstance(model2, MockWorldModel)
        
        # Test unknown model type
        with pytest.raises(ValueError) as exc_info:
            WorldModelFactory.create_model("unknown", config)
        assert "Unknown model type 'unknown'" in str(exc_info.value)
        assert "Available types:" in str(exc_info.value)
    
    def test_factory_registry_management(self):
        """Test factory registry management methods."""
        # Initially empty (after setup)
        assert len(WorldModelFactory.get_registered_types()) == 0
        
        # Register models
        WorldModelFactory.register("model1", MockWorldModel)
        WorldModelFactory.register("model2", MockWorldModel)
        
        # Check registry
        types = WorldModelFactory.get_registered_types()
        assert len(types) == 2
        assert "model1" in types
        assert "model2" in types
        
        # Clear registry
        WorldModelFactory.clear_registry()
        assert len(WorldModelFactory.get_registered_types()) == 0
        assert not WorldModelFactory.is_registered("model1")


class TestMockWorldModel:
    """Test cases for MockWorldModel implementation."""
    
    @pytest_asyncio.fixture
    async def mock_model(self):
        """Create and initialize a mock model for testing."""
        model = MockWorldModel(config={"test": "config"})
        await model.initialize()
        yield model
        await model.shutdown()
    
    @pytest.mark.asyncio
    async def test_mock_model_lifecycle(self):
        """Test mock model initialization and shutdown."""
        model = MockWorldModel(config={})
        
        # Initially not initialized
        assert not model.is_initialized
        
        # Initialize
        await model.initialize()
        assert model.is_initialized
        
        # Health status
        health = await model.get_health_status()
        assert health["status"] == "healthy"
        assert health["model_type"] == "mock"
        
        # Shutdown
        await model.shutdown()
        assert not model.is_initialized
    
    @pytest.mark.asyncio
    async def test_mock_model_update_state(self, mock_model):
        """Test mock model state updates."""
        # Create a knowledge event
        event = KnowledgeEvent(
            source="test_source",
            event_type="telemetry",
            data={"metric": "cpu", "value": 80}
        )
        
        # Should not raise exception
        await mock_model.update_state(event)
    
    @pytest.mark.asyncio
    async def test_mock_model_calibrate(self, mock_model):
        """Test mock model calibration."""
        # Create a calibration event
        event = CalibrationEvent(
            prediction_id="pred-123",
            actual_outcome={"cpu": 75.0},
            predicted_outcome={"cpu": 80.0},
            accuracy_metrics={"mse": 0.1, "accuracy": 0.9}
        )
        
        # Should not raise exception
        await mock_model.calibrate(event)
    
    @pytest.mark.asyncio
    async def test_mock_model_query(self, mock_model):
        """Test mock model queries."""
        request = QueryRequest(
            query_id="q1",
            query_type="current_state",
            query_content="What is the system status?"
        )
        
        response = await mock_model.query_state(request)
        
        assert response.query_id == "q1"
        assert response.success is True
        assert "Mock response" in response.result
        assert response.confidence == 0.8
        assert response.explanation is not None
    
    @pytest.mark.asyncio
    async def test_mock_model_simulate(self, mock_model):
        """Test mock model simulation."""
        request = SimulationRequest(
            simulation_id="s1",
            simulation_type="forecast",
            horizon_minutes=60
        )
        
        response = await mock_model.simulate(request)
        
        assert response.simulation_id == "s1"
        assert response.success is True
        assert len(response.future_states) == 2
        assert response.confidence == 0.7
        assert response.uncertainty_lower == 0.6
        assert response.uncertainty_upper == 0.8
        assert "Mock simulation" in response.explanation
    
    @pytest.mark.asyncio
    async def test_mock_model_diagnose(self, mock_model):
        """Test mock model diagnosis."""
        request = DiagnosisRequest(
            diagnosis_id="d1",
            anomaly_description="System performance degraded"
        )
        
        response = await mock_model.diagnose(request)
        
        assert response.diagnosis_id == "d1"
        assert response.success is True
        assert len(response.hypotheses) == 3
        assert "Resource exhaustion" in response.causal_chain
        assert response.confidence == 0.75
        assert len(response.supporting_evidence) == 3
    
    @pytest.mark.asyncio
    async def test_mock_model_reload(self, mock_model):
        """Test mock model reload."""
        result = await mock_model.reload_model()
        assert result is True
    
    def test_mock_model_sync_wrappers(self):
        """Test synchronous wrapper methods."""
        model = MockWorldModel(config={})
        
        # Test sync wrappers (these will run the async methods)
        # Note: In a real test environment, you might want to mock asyncio.run
        # For now, we'll just test that the methods exist and are callable
        assert hasattr(model, 'update_state_sync')
        assert hasattr(model, 'calibrate_sync')
        assert hasattr(model, 'query_state_sync')
        assert hasattr(model, 'simulate_sync')
        assert hasattr(model, 'diagnose_sync')
        assert hasattr(model, 'get_health_status_sync')
        assert hasattr(model, 'reload_model_sync')
        
        # Test that they are callable
        assert callable(model.update_state_sync)
        assert callable(model.query_state_sync)


class TestWorldModelIntegration:
    """Test integration between World Model and Digital Twin events."""
    
    @pytest.mark.asyncio
    async def test_world_model_with_real_events(self):
        """Test World Model with real Digital Twin events."""
        model = MockWorldModel(config={})
        await model.initialize()
        
        try:
            # Test with KnowledgeEvent containing telemetry
            from polaris.models.telemetry import TelemetryEvent
            
            telemetry = TelemetryEvent(
                name="cpu.usage",
                value=85.5,
                unit="percent",
                source="monitor"
            )
            
            knowledge_event = KnowledgeEvent(
                source="monitor_adapter",
                event_type="telemetry",
                data=telemetry
            )
            
            # Should process without error
            await model.update_state(knowledge_event)
            
            # Test with CalibrationEvent
            calibration_event = CalibrationEvent(
                prediction_id="pred-456",
                actual_outcome={"cpu": 82.0, "memory": 65.0},
                predicted_outcome={"cpu": 85.0, "memory": 70.0},
                accuracy_metrics={"mse": 0.05, "mae": 0.03}
            )
            
            # Should process without error
            await model.calibrate(calibration_event)
            
        finally:
            await model.shutdown()
    
    def test_factory_with_mock_model_registration(self):
        """Test that mock model is properly registered in factory."""
        # Mock model should be registered by default
        assert WorldModelFactory.is_registered("mock")
        
        # Should be able to create mock model
        model = WorldModelFactory.create_model("mock", {"test": "config"})
        assert isinstance(model, MockWorldModel)
        assert model.config["test"] == "config"


class TestWorldModelExceptions:
    """Test World Model exception handling."""
    
    def test_world_model_exceptions(self):
        """Test World Model exception hierarchy."""
        # Test base exception
        base_error = WorldModelError("Base error")
        assert str(base_error) == "Base error"
        assert isinstance(base_error, Exception)
        
        # Test initialization error
        init_error = WorldModelInitializationError("Init failed")
        assert str(init_error) == "Init failed"
        assert isinstance(init_error, WorldModelError)
        
        # Test operation error
        op_error = WorldModelOperationError("Operation failed")
        assert str(op_error) == "Operation failed"
        assert isinstance(op_error, WorldModelError)
    
    def test_factory_initialization_error(self):
        """Test factory initialization error handling."""
        # Create a mock class that raises an exception during initialization
        class FailingWorldModel(WorldModel):
            def __init__(self, config, logger=None):
                raise RuntimeError("Initialization failed")
            
            async def initialize(self): pass
            async def shutdown(self): pass
            async def update_state(self, event): pass
            async def calibrate(self, event): pass
            async def query_state(self, request): pass
            async def simulate(self, request): pass
            async def diagnose(self, request): pass
            async def get_health_status(self): pass
            async def reload_model(self): pass
        
        WorldModelFactory.register("failing", FailingWorldModel)
        
        with pytest.raises(WorldModelInitializationError) as exc_info:
            WorldModelFactory.create_model("failing", {})
        
        assert "Failed to create failing model" in str(exc_info.value)
        assert "Initialization failed" in str(exc_info.value)