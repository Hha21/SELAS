"""
Unit tests for Protocol Buffer wrapper classes.

Tests conversion between Pydantic models and Protocol Buffer messages.
"""

import sys
from pathlib import Path
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, Mock

# Add parent directory to path to import from polaris
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from polaris.proto.wrappers import ProtobufConverter, GrpcServiceWrapper
from polaris.proto.digital_twin_pb2 import (
    QueryRequest as PBQueryRequest,
    QueryResponse as PBQueryResponse,
    SimulationRequest as PBSimulationRequest,
    SimulationResponse as PBSimulationResponse,
    DiagnosisRequest as PBDiagnosisRequest,
    DiagnosisResponse as PBDiagnosisResponse,
    ManagementRequest as PBManagementRequest
)

from polaris.models.world_model import (
    QueryRequest, QueryResponse,
    SimulationRequest, SimulationResponse,
    DiagnosisRequest, DiagnosisResponse,
)

from polaris.models.mock_world_model import MockWorldModel


class TestProtobufConverter:
    """Test cases for ProtobufConverter."""
    
    def test_query_request_conversion(self):
        """Test QueryRequest conversion between Pydantic and Protobuf."""
        # Create Pydantic model
        pydantic_request = QueryRequest(
            query_id="q123",
            query_type="current_state",
            query_content="What is the CPU usage?",
            parameters={"system": "prod", "metric": "cpu"}
        )
        
        # Convert to protobuf
        pb_request = ProtobufConverter.query_request_to_pb(pydantic_request)
        
        assert pb_request.query_id == "q123"
        assert pb_request.query_type == "current_state"
        assert pb_request.query_content == "What is the CPU usage?"
        assert pb_request.parameters["system"] == "prod"
        assert pb_request.parameters["metric"] == "cpu"
        assert pb_request.timestamp == pydantic_request.timestamp
        
        # Convert back to Pydantic
        converted_back = ProtobufConverter.query_request_from_pb(pb_request)
        
        assert converted_back.query_id == pydantic_request.query_id
        assert converted_back.query_type == pydantic_request.query_type
        assert converted_back.query_content == pydantic_request.query_content
        assert converted_back.parameters == pydantic_request.parameters
    
    def test_query_response_conversion(self):
        """Test QueryResponse conversion between Pydantic and Protobuf."""
        # Create Pydantic model
        pydantic_response = QueryResponse(
            query_id="q123",
            success=True,
            result="CPU usage is 75%",
            confidence=0.9,
            explanation="Based on latest telemetry",
            metadata={"source": "monitor", "timestamp": "2025-08-15T10:30:00Z"}
        )
        
        # Convert to protobuf
        pb_response = ProtobufConverter.query_response_to_pb(pydantic_response)
        
        assert pb_response.query_id == "q123"
        assert pb_response.success is True
        assert pb_response.result == "CPU usage is 75%"
        assert pb_response.confidence == 0.9
        assert pb_response.explanation == "Based on latest telemetry"
        assert pb_response.metadata["source"] == "monitor"
        
        # Convert back to Pydantic
        converted_back = ProtobufConverter.query_response_from_pb(pb_response)
        
        assert converted_back.query_id == pydantic_response.query_id
        assert converted_back.success == pydantic_response.success
        assert converted_back.result == pydantic_response.result
        assert converted_back.confidence == pydantic_response.confidence
        assert converted_back.explanation == pydantic_response.explanation
        assert converted_back.metadata == pydantic_response.metadata
    
    def test_simulation_request_conversion(self):
        """Test SimulationRequest conversion between Pydantic and Protobuf."""
        # Create Pydantic model
        pydantic_request = SimulationRequest(
            simulation_id="s123",
            simulation_type="forecast",
            actions=[
                {
                    "action_id": "a1",
                    "action_type": "SCALE_UP",
                    "target": "web-servers",
                    "params": {"count": "2", "instance_type": "m5.large"},
                    "priority": "high",
                    "timeout": 60.0
                }
            ],
            horizon_minutes=30,
            parameters={"confidence_level": "0.95"}
        )
        
        # Convert to protobuf
        pb_request = ProtobufConverter.simulation_request_to_pb(pydantic_request)
        
        assert pb_request.simulation_id == "s123"
        assert pb_request.simulation_type == "forecast"
        assert pb_request.horizon_minutes == 30
        assert len(pb_request.actions) == 1
        
        pb_action = pb_request.actions[0]
        assert pb_action.action_id == "a1"
        assert pb_action.action_type == "SCALE_UP"
        assert pb_action.target == "web-servers"
        assert pb_action.params["count"] == "2"
        assert pb_action.priority == "high"
        assert pb_action.timeout == 60.0
        
        # Convert back to Pydantic
        converted_back = ProtobufConverter.simulation_request_from_pb(pb_request)
        
        assert converted_back.simulation_id == pydantic_request.simulation_id
        assert converted_back.simulation_type == pydantic_request.simulation_type
        assert converted_back.horizon_minutes == pydantic_request.horizon_minutes
        assert len(converted_back.actions) == 1
        assert converted_back.actions[0]["action_id"] == "a1"
        assert converted_back.actions[0]["params"]["count"] == "2"
    
    def test_simulation_response_conversion(self):
        """Test SimulationResponse conversion between Pydantic and Protobuf."""
        # Create Pydantic model
        pydantic_response = SimulationResponse(
            simulation_id="s123",
            success=True,
            future_states=[
                {"time": "+15min", "cpu": 65.0, "memory": 70.0, "confidence": 0.9},
                {"time": "+30min", "cpu": 60.0, "memory": 68.0, "confidence": 0.8}
            ],
            confidence=0.85,
            uncertainty_lower=0.75,
            uncertainty_upper=0.95,
            explanation="Forecast shows decreasing resource usage",
            impact_estimates={
                "cost_impact": 150.0,
                "performance_impact": 0.1,
                "reliability_impact": 0.05,
                "cost_currency": "USD"
            },
            metadata={"model_version": "1.0"}
        )
        
        # Convert to protobuf
        pb_response = ProtobufConverter.simulation_response_to_pb(pydantic_response)
        
        assert pb_response.simulation_id == "s123"
        assert pb_response.success is True
        assert pb_response.confidence == 0.85
        assert pb_response.uncertainty_lower == 0.75
        assert pb_response.uncertainty_upper == 0.95
        assert pb_response.explanation == "Forecast shows decreasing resource usage"
        
        # Check future states
        assert len(pb_response.future_states) == 2
        state1 = pb_response.future_states[0]
        assert state1.timestamp == "+15min"
        assert state1.metrics["cpu"] == 65.0
        assert state1.metrics["memory"] == 70.0
        assert state1.confidence == 0.9
        
        # Check impact estimates
        assert pb_response.impact_estimates.cost_impact == 150.0
        assert pb_response.impact_estimates.cost_currency == "USD"
        
        # Convert back to Pydantic
        converted_back = ProtobufConverter.simulation_response_from_pb(pb_response)
        
        assert converted_back.simulation_id == pydantic_response.simulation_id
        assert converted_back.success == pydantic_response.success
        assert len(converted_back.future_states) == 2
        assert converted_back.future_states[0]["cpu"] == 65.0
        assert converted_back.impact_estimates["cost_impact"] == 150.0
    
    def test_diagnosis_request_conversion(self):
        """Test DiagnosisRequest conversion between Pydantic and Protobuf."""
        # Create Pydantic model
        pydantic_request = DiagnosisRequest(
            diagnosis_id="d123",
            anomaly_description="High response times detected",
            context={"severity": "high", "duration": "30min", "affected_services": "web,api"}
        )
        
        # Convert to protobuf
        pb_request = ProtobufConverter.diagnosis_request_to_pb(pydantic_request)
        
        assert pb_request.diagnosis_id == "d123"
        assert pb_request.anomaly_description == "High response times detected"
        assert pb_request.context["severity"] == "high"
        assert pb_request.context["duration"] == "30min"
        
        # Convert back to Pydantic
        converted_back = ProtobufConverter.diagnosis_request_from_pb(pb_request)
        
        assert converted_back.diagnosis_id == pydantic_request.diagnosis_id
        assert converted_back.anomaly_description == pydantic_request.anomaly_description
        assert converted_back.context == pydantic_request.context
    
    def test_diagnosis_response_conversion(self):
        """Test DiagnosisResponse conversion between Pydantic and Protobuf."""
        # Create Pydantic model
        pydantic_response = DiagnosisResponse(
            diagnosis_id="d123",
            success=True,
            hypotheses=["Database overload", "Network congestion", "Memory leak"],
            causal_chain="Load spike -> DB bottleneck -> Response delays",
            confidence=0.8,
            explanation="Analysis indicates database performance issues",
            supporting_evidence=["CPU metrics", "DB query times", "Network latency"],
            metadata={"analysis_duration": "5.2s"}
        )
        
        # Convert to protobuf
        pb_response = ProtobufConverter.diagnosis_response_to_pb(pydantic_response)
        
        assert pb_response.diagnosis_id == "d123"
        assert pb_response.success is True
        assert pb_response.causal_chain == "Load spike -> DB bottleneck -> Response delays"
        assert pb_response.confidence == 0.8
        assert pb_response.explanation == "Analysis indicates database performance issues"
        
        # Check hypotheses
        assert len(pb_response.hypotheses) == 3
        assert pb_response.hypotheses[0].hypothesis == "Database overload"
        assert pb_response.hypotheses[0].rank == 1
        
        # Check supporting evidence
        assert len(pb_response.supporting_evidence) == 3
        assert "CPU metrics" in pb_response.supporting_evidence
        
        # Convert back to Pydantic
        converted_back = ProtobufConverter.diagnosis_response_from_pb(pb_response)
        
        assert converted_back.diagnosis_id == pydantic_response.diagnosis_id
        assert converted_back.success == pydantic_response.success
        assert len(converted_back.hypotheses) == 3
        assert converted_back.hypotheses[0] == "Database overload"
        assert converted_back.causal_chain == pydantic_response.causal_chain
        assert len(converted_back.supporting_evidence) == 3
    
    def test_health_status_conversion(self):
        """Test health status conversion between dict and Protobuf."""
        # Create health dict
        health_dict = {
            "status": "healthy",
            "last_check": "2025-08-15T10:30:00Z",
            "performance_metrics": {"queries_per_sec": 100.0, "avg_response_time": 0.05},
            "issues": [],
            "model_type": "mock",
            "model_version": "1.0.0"
        }
        
        # Convert to protobuf
        pb_health = ProtobufConverter.health_status_from_dict(health_dict)
        
        assert pb_health.status == "healthy"
        assert pb_health.last_check == "2025-08-15T10:30:00Z"
        assert pb_health.performance_metrics["queries_per_sec"] == 100.0
        assert pb_health.model_type == "mock"
        assert pb_health.model_version == "1.0.0"
        assert len(pb_health.issues) == 0
        
        # Convert back to dict
        converted_back = ProtobufConverter.health_status_to_dict(pb_health)
        
        assert converted_back["status"] == health_dict["status"]
        assert converted_back["model_type"] == health_dict["model_type"]
        assert converted_back["performance_metrics"]["queries_per_sec"] == 100.0


class TestGrpcServiceWrapper:
    """Test cases for GrpcServiceWrapper."""
    
    @pytest.fixture
    def mock_world_model(self):
        """Create a mock world model for testing."""
        model = AsyncMock(spec=MockWorldModel)
        model.query_state = AsyncMock()
        model.simulate = AsyncMock()
        model.diagnose = AsyncMock()
        model.get_health_status = AsyncMock()
        model.reload_model = AsyncMock()
        return model
    
    @pytest.fixture
    def grpc_wrapper(self, mock_world_model):
        """Create a gRPC service wrapper with mock world model."""
        return GrpcServiceWrapper(mock_world_model)
    
    @pytest.mark.asyncio
    async def test_grpc_query_success(self, grpc_wrapper, mock_world_model):
        """Test successful gRPC Query handling."""
        # Setup mock response
        mock_response = QueryResponse(
            query_id="q123",
            success=True,
            result="CPU usage is 75%",
            confidence=0.9,
            explanation="Mock response"
        )
        mock_world_model.query_state.return_value = mock_response
        
        # Create protobuf request
        pb_request = PBQueryRequest()
        pb_request.query_id = "q123"
        pb_request.query_type = "current_state"
        pb_request.query_content = "What is CPU usage?"
        
        # Call gRPC method
        pb_response = await grpc_wrapper.Query(pb_request, None)
        
        # Verify response
        assert pb_response.query_id == "q123"
        assert pb_response.success is True
        assert pb_response.result == "CPU usage is 75%"
        assert pb_response.confidence == 0.9
        
        # Verify world model was called
        mock_world_model.query_state.assert_called_once()
        call_args = mock_world_model.query_state.call_args[0][0]
        assert call_args.query_id == "q123"
        assert call_args.query_type == "current_state"
    
    @pytest.mark.asyncio
    async def test_grpc_query_error(self, grpc_wrapper, mock_world_model):
        """Test gRPC Query error handling."""
        # Setup mock to raise exception
        mock_world_model.query_state.side_effect = Exception("Query failed")
        
        # Create protobuf request
        pb_request = PBQueryRequest()
        pb_request.query_id = "q123"
        pb_request.query_type = "current_state"
        pb_request.query_content = "What is CPU usage?"
        
        # Call gRPC method
        pb_response = await grpc_wrapper.Query(pb_request, None)
        
        # Verify error response
        assert pb_response.query_id == "q123"
        assert pb_response.success is False
        assert "Query failed" in pb_response.explanation
        assert pb_response.confidence == 0.0
    
    @pytest.mark.asyncio
    async def test_grpc_simulate_success(self, grpc_wrapper, mock_world_model):
        """Test successful gRPC Simulate handling."""
        # Setup mock response
        mock_response = SimulationResponse(
            simulation_id="s123",
            success=True,
            future_states=[{"time": "+30min", "cpu": 70.0}],
            confidence=0.8,
            uncertainty_lower=0.7,
            uncertainty_upper=0.9,
            explanation="Mock simulation"
        )
        mock_world_model.simulate.return_value = mock_response
        
        # Create protobuf request
        pb_request = PBSimulationRequest()
        pb_request.simulation_id = "s123"
        pb_request.simulation_type = "forecast"
        pb_request.horizon_minutes = 30
        
        # Call gRPC method
        pb_response = await grpc_wrapper.Simulate(pb_request, None)
        
        # Verify response
        assert pb_response.simulation_id == "s123"
        assert pb_response.success is True
        assert pb_response.confidence == 0.8
        assert len(pb_response.future_states) == 1
        
        # Verify world model was called
        mock_world_model.simulate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_grpc_diagnose_success(self, grpc_wrapper, mock_world_model):
        """Test successful gRPC Diagnose handling."""
        # Setup mock response
        mock_response = DiagnosisResponse(
            diagnosis_id="d123",
            success=True,
            hypotheses=["Database overload", "Network issues"],
            causal_chain="Load -> DB bottleneck -> Delays",
            confidence=0.75,
            explanation="Mock diagnosis"
        )
        mock_world_model.diagnose.return_value = mock_response
        
        # Create protobuf request
        pb_request = PBDiagnosisRequest()
        pb_request.diagnosis_id = "d123"
        pb_request.anomaly_description = "High response times"
        
        # Call gRPC method
        pb_response = await grpc_wrapper.Diagnose(pb_request, None)
        
        # Verify response
        assert pb_response.diagnosis_id == "d123"
        assert pb_response.success is True
        assert pb_response.confidence == 0.75
        assert len(pb_response.hypotheses) == 2
        
        # Verify world model was called
        mock_world_model.diagnose.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_grpc_manage_health_check(self, grpc_wrapper, mock_world_model):
        """Test gRPC Management health check operation."""
        # Setup mock response
        mock_health = {
            "status": "healthy",
            "last_check": "2025-08-15T10:30:00Z",
            "model_type": "mock",
            "model_version": "1.0.0",
            "metrics": {"queries_processed": 100}
        }
        mock_world_model.get_health_status.return_value = mock_health
        
        # Create protobuf request
        pb_request = PBManagementRequest()
        pb_request.request_id = "m123"
        pb_request.operation = "health_check"
        
        # Call gRPC method
        pb_response = await grpc_wrapper.Manage(pb_request, None)
        
        # Verify response
        assert pb_response.request_id == "m123"
        assert pb_response.success is True
        assert "Health check completed" in pb_response.result
        assert pb_response.health_status.status == "healthy"
        assert pb_response.health_status.model_type == "mock"
        
        # Verify world model was called
        mock_world_model.get_health_status.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_grpc_manage_reload_model(self, grpc_wrapper, mock_world_model):
        """Test gRPC Management model reload operation."""
        # Setup mock response
        mock_world_model.reload_model.return_value = True
        
        # Create protobuf request
        pb_request = PBManagementRequest()
        pb_request.request_id = "m123"
        pb_request.operation = "reload_model"
        
        # Call gRPC method
        pb_response = await grpc_wrapper.Manage(pb_request, None)
        
        # Verify response
        assert pb_response.request_id == "m123"
        assert pb_response.success is True
        assert "Model reloaded" in pb_response.result
        
        # Verify world model was called
        mock_world_model.reload_model.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_grpc_manage_unknown_operation(self, grpc_wrapper, mock_world_model):
        """Test gRPC Management with unknown operation."""
        # Create protobuf request
        pb_request = PBManagementRequest()
        pb_request.request_id = "m123"
        pb_request.operation = "unknown_operation"
        
        # Call gRPC method
        pb_response = await grpc_wrapper.Manage(pb_request, None)
        
        # Verify error response
        assert pb_response.request_id == "m123"
        assert pb_response.success is False
        assert "Unknown operation" in pb_response.result