"""
Wrapper classes to integrate Protocol Buffer messages with Pydantic models.

This module provides conversion utilities between POLARIS Pydantic models
and Protocol Buffer messages for gRPC communication.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from .digital_twin_pb2 import (
    QueryRequest as PBQueryRequest,
    QueryResponse as PBQueryResponse,
    SimulationRequest as PBSimulationRequest,
    SimulationResponse as PBSimulationResponse,
    DiagnosisRequest as PBDiagnosisRequest,
    DiagnosisResponse as PBDiagnosisResponse,
    ManagementRequest as PBManagementRequest,
    ManagementResponse as PBManagementResponse,
    ControlAction as PBControlAction,
    PredictedState as PBPredictedState,
    SimulationMetrics as PBSimulationMetrics,
    CostPerformanceReliability as PBCostPerformanceReliability,
    CausalHypothesis as PBCausalHypothesis,
    HealthStatus as PBHealthStatus
)

from ..models.world_model import (
    QueryRequest, QueryResponse,
    SimulationRequest, SimulationResponse,
    DiagnosisRequest, DiagnosisResponse
)


class ProtobufConverter:
    """Utility class for converting between Pydantic models and Protocol Buffer messages."""
    
    @staticmethod
    def query_request_to_pb(request: QueryRequest) -> PBQueryRequest:
        """Convert Pydantic QueryRequest to Protocol Buffer message."""
        pb_request = PBQueryRequest()
        pb_request.query_id = request.query_id
        pb_request.query_type = request.query_type
        pb_request.query_content = request.query_content
        pb_request.timestamp = request.timestamp
        
        # Convert parameters dict
        for key, value in request.parameters.items():
            pb_request.parameters[key] = str(value)
        
        return pb_request
    
    @staticmethod
    def query_request_from_pb(pb_request: PBQueryRequest) -> QueryRequest:
        """Convert Protocol Buffer QueryRequest to Pydantic model."""
        return QueryRequest(
            query_id=pb_request.query_id,
            query_type=pb_request.query_type,
            query_content=pb_request.query_content,
            parameters=dict(pb_request.parameters),
            timestamp=pb_request.timestamp if pb_request.timestamp else None
        )
    
    @staticmethod
    def query_response_to_pb(response: QueryResponse) -> PBQueryResponse:
        """Convert Pydantic QueryResponse to Protocol Buffer message."""
        pb_response = PBQueryResponse()
        pb_response.query_id = response.query_id
        pb_response.success = response.success
        pb_response.result = response.result
        pb_response.confidence = response.confidence
        pb_response.explanation = response.explanation
        pb_response.timestamp = response.timestamp
        
        # Convert metadata dict
        for key, value in response.metadata.items():
            pb_response.metadata[key] = str(value)
        
        return pb_response
    
    @staticmethod
    def query_response_from_pb(pb_response: PBQueryResponse) -> QueryResponse:
        """Convert Protocol Buffer QueryResponse to Pydantic model."""
        return QueryResponse(
            query_id=pb_response.query_id,
            success=pb_response.success,
            result=pb_response.result,
            confidence=pb_response.confidence,
            explanation=pb_response.explanation,
            timestamp=pb_response.timestamp if pb_response.timestamp else None,
            metadata=dict(pb_response.metadata)
        )
    
    @staticmethod
    def simulation_request_to_pb(request: SimulationRequest) -> PBSimulationRequest:
        """Convert Pydantic SimulationRequest to Protocol Buffer message."""
        pb_request = PBSimulationRequest()
        pb_request.simulation_id = request.simulation_id
        pb_request.simulation_type = request.simulation_type
        pb_request.horizon_minutes = request.horizon_minutes
        pb_request.timestamp = request.timestamp
        
        # Convert actions list
        for action in request.actions:
            pb_action = pb_request.actions.add()
            pb_action.action_id = action.get("action_id", "")
            pb_action.action_type = action.get("action_type", "")
            pb_action.target = action.get("target", "")
            pb_action.priority = action.get("priority", "normal")
            pb_action.timeout = float(action.get("timeout", 30.0))
            
            # Convert action params
            params = action.get("params", {})
            for key, value in params.items():
                pb_action.params[key] = str(value)
        
        # Convert parameters dict
        for key, value in request.parameters.items():
            pb_request.parameters[key] = str(value)
        
        return pb_request
    
    @staticmethod
    def simulation_request_from_pb(pb_request: PBSimulationRequest) -> SimulationRequest:
        """Convert Protocol Buffer SimulationRequest to Pydantic model."""
        # Convert actions
        actions = []
        for pb_action in pb_request.actions:
            action = {
                "action_id": pb_action.action_id,
                "action_type": pb_action.action_type,
                "target": pb_action.target,
                "priority": pb_action.priority,
                "timeout": pb_action.timeout,
                "params": dict(pb_action.params)
            }
            actions.append(action)
        
        return SimulationRequest(
            simulation_id=pb_request.simulation_id,
            simulation_type=pb_request.simulation_type,
            actions=actions,
            horizon_minutes=pb_request.horizon_minutes,
            parameters=dict(pb_request.parameters),
            timestamp=pb_request.timestamp if pb_request.timestamp else None
        )
    
    @staticmethod
    def simulation_response_to_pb(response: SimulationResponse) -> PBSimulationResponse:
        """Convert Pydantic SimulationResponse to Protocol Buffer message."""
        pb_response = PBSimulationResponse()
        pb_response.simulation_id = response.simulation_id
        pb_response.success = response.success
        pb_response.confidence = response.confidence
        pb_response.uncertainty_lower = response.uncertainty_lower
        pb_response.uncertainty_upper = response.uncertainty_upper
        pb_response.explanation = response.explanation
        pb_response.timestamp = response.timestamp
        
        # Convert future states
        for state in response.future_states:
            pb_state = pb_response.future_states.add()
            pb_state.timestamp = state.get("time", "")
            pb_state.description = state.get("description", "")
            pb_state.confidence = float(state.get("confidence", 1.0))
            
            # Convert metrics
            for key, value in state.items():
                if key not in ["time", "description", "confidence"] and isinstance(value, (int, float)):
                    pb_state.metrics[key] = float(value)
        
        # Convert impact estimates
        if response.impact_estimates:
            pb_impact = pb_response.impact_estimates
            pb_impact.cost_impact = float(response.impact_estimates.get("cost_impact", 0.0))
            pb_impact.performance_impact = float(response.impact_estimates.get("performance_impact", 0.0))
            pb_impact.reliability_impact = float(response.impact_estimates.get("reliability_impact", 0.0))
            pb_impact.cost_currency = response.impact_estimates.get("cost_currency", "USD")
            pb_impact.impact_description = response.impact_estimates.get("impact_description", "")
        
        # Convert metadata
        for key, value in response.metadata.items():
            pb_response.metadata[key] = str(value)
        
        return pb_response
    
    @staticmethod
    def simulation_response_from_pb(pb_response: PBSimulationResponse) -> SimulationResponse:
        """Convert Protocol Buffer SimulationResponse to Pydantic model."""
        # Convert future states
        future_states = []
        for pb_state in pb_response.future_states:
            state = {
                "time": pb_state.timestamp,
                "description": pb_state.description,
                "confidence": pb_state.confidence
            }
            # Add metrics
            state.update(dict(pb_state.metrics))
            future_states.append(state)
        
        # Convert impact estimates
        impact_estimates = {}
        if pb_response.HasField("impact_estimates"):
            pb_impact = pb_response.impact_estimates
            impact_estimates = {
                "cost_impact": pb_impact.cost_impact,
                "performance_impact": pb_impact.performance_impact,
                "reliability_impact": pb_impact.reliability_impact,
                "cost_currency": pb_impact.cost_currency,
                "impact_description": pb_impact.impact_description
            }
        
        return SimulationResponse(
            simulation_id=pb_response.simulation_id,
            success=pb_response.success,
            future_states=future_states,
            confidence=pb_response.confidence,
            uncertainty_lower=pb_response.uncertainty_lower,
            uncertainty_upper=pb_response.uncertainty_upper,
            explanation=pb_response.explanation,
            impact_estimates=impact_estimates,
            timestamp=pb_response.timestamp if pb_response.timestamp else None,
            metadata=dict(pb_response.metadata)
        )
    
    @staticmethod
    def diagnosis_request_to_pb(request: DiagnosisRequest) -> PBDiagnosisRequest:
        """Convert Pydantic DiagnosisRequest to Protocol Buffer message."""
        pb_request = PBDiagnosisRequest()
        pb_request.diagnosis_id = request.diagnosis_id
        pb_request.anomaly_description = request.anomaly_description
        pb_request.timestamp = request.timestamp
        
        # Convert context dict
        for key, value in request.context.items():
            pb_request.context[key] = str(value)
        
        return pb_request
    
    @staticmethod
    def diagnosis_request_from_pb(pb_request: PBDiagnosisRequest) -> DiagnosisRequest:
        """Convert Protocol Buffer DiagnosisRequest to Pydantic model."""
        return DiagnosisRequest(
            diagnosis_id=pb_request.diagnosis_id,
            anomaly_description=pb_request.anomaly_description,
            context=dict(pb_request.context),
            timestamp=pb_request.timestamp if pb_request.timestamp else None
        )
    
    @staticmethod
    def diagnosis_response_to_pb(response: DiagnosisResponse) -> PBDiagnosisResponse:
        """Convert Pydantic DiagnosisResponse to Protocol Buffer message."""
        pb_response = PBDiagnosisResponse()
        pb_response.diagnosis_id = response.diagnosis_id
        pb_response.success = response.success
        pb_response.causal_chain = response.causal_chain
        pb_response.confidence = response.confidence
        pb_response.explanation = response.explanation
        pb_response.timestamp = response.timestamp
        
        # Convert hypotheses
        for i, hypothesis in enumerate(response.hypotheses):
            pb_hypothesis = pb_response.hypotheses.add()
            pb_hypothesis.hypothesis = str(hypothesis)
            pb_hypothesis.probability = 1.0 / (i + 1)  # Simple ranking-based probability
            pb_hypothesis.reasoning = f"Ranked #{i+1} based on analysis"
            pb_hypothesis.rank = i + 1
        
        # Convert supporting evidence
        pb_response.supporting_evidence.extend(response.supporting_evidence)
        
        # Convert metadata
        for key, value in response.metadata.items():
            pb_response.metadata[key] = str(value)
        
        return pb_response
    
    @staticmethod
    def diagnosis_response_from_pb(pb_response: PBDiagnosisResponse) -> DiagnosisResponse:
        """Convert Protocol Buffer DiagnosisResponse to Pydantic model."""
        # Convert hypotheses (extract just the hypothesis text)
        hypotheses = [pb_hyp.hypothesis for pb_hyp in pb_response.hypotheses]
        
        return DiagnosisResponse(
            diagnosis_id=pb_response.diagnosis_id,
            success=pb_response.success,
            hypotheses=hypotheses,
            causal_chain=pb_response.causal_chain,
            confidence=pb_response.confidence,
            explanation=pb_response.explanation,
            supporting_evidence=list(pb_response.supporting_evidence),
            timestamp=pb_response.timestamp if pb_response.timestamp else None,
            metadata=dict(pb_response.metadata)
        )
    
    @staticmethod
    def health_status_to_dict(pb_health: PBHealthStatus) -> Dict[str, Any]:
        """Convert Protocol Buffer HealthStatus to dictionary."""
        return {
            "status": pb_health.status,
            "last_check": pb_health.last_check,
            "performance_metrics": dict(pb_health.performance_metrics),
            "issues": list(pb_health.issues),
            "model_type": pb_health.model_type,
            "model_version": pb_health.model_version
        }
    
    @staticmethod
    def health_status_from_dict(health_dict: Dict[str, Any]) -> PBHealthStatus:
        """Convert dictionary to Protocol Buffer HealthStatus."""
        pb_health = PBHealthStatus()
        pb_health.status = health_dict.get("status", "unknown")
        pb_health.last_check = health_dict.get("last_check", "")
        pb_health.model_type = health_dict.get("model_type", "")
        pb_health.model_version = health_dict.get("model_version", "")
        
        # Convert performance metrics
        for key, value in health_dict.get("performance_metrics", {}).items():
            pb_health.performance_metrics[key] = float(value)
        
        # Convert issues
        pb_health.issues.extend(health_dict.get("issues", []))
        
        return pb_health


class GrpcServiceWrapper:
    """
    Base wrapper class for gRPC service implementations.
    
    This class provides common functionality for wrapping World Model
    implementations with gRPC service interfaces.
    """
    
    def __init__(self, world_model):
        """Initialize with a World Model implementation.
        
        Args:
            world_model: WorldModel implementation instance
        """
        self.world_model = world_model
        self.converter = ProtobufConverter()
    
    async def Query(self, request: PBQueryRequest, context) -> PBQueryResponse:
        """Handle gRPC Query requests."""
        try:
            # Convert protobuf to Pydantic
            pydantic_request = self.converter.query_request_from_pb(request)
            
            # Call world model
            pydantic_response = await self.world_model.query_state(pydantic_request)
            
            # Convert back to protobuf
            return self.converter.query_response_to_pb(pydantic_response)
            
        except Exception as e:
            # Return error response
            error_response = QueryResponse(
                query_id=request.query_id,
                success=False,
                result="",
                confidence=0.0,
                explanation=f"Query failed: {str(e)}"
            )
            return self.converter.query_response_to_pb(error_response)
    
    async def Simulate(self, request: PBSimulationRequest, context) -> PBSimulationResponse:
        """Handle gRPC Simulate requests."""
        try:
            # Convert protobuf to Pydantic
            pydantic_request = self.converter.simulation_request_from_pb(request)
            
            # Call world model
            pydantic_response = await self.world_model.simulate(pydantic_request)
            
            # Convert back to protobuf
            return self.converter.simulation_response_to_pb(pydantic_response)
            
        except Exception as e:
            # Return error response
            error_response = SimulationResponse(
                simulation_id=request.simulation_id,
                success=False,
                future_states=[],
                confidence=0.0,
                uncertainty_lower=0.0,
                uncertainty_upper=0.0,
                explanation=f"Simulation failed: {str(e)}"
            )
            return self.converter.simulation_response_to_pb(error_response)
    
    async def Diagnose(self, request: PBDiagnosisRequest, context) -> PBDiagnosisResponse:
        """Handle gRPC Diagnose requests."""
        try:
            # Convert protobuf to Pydantic
            pydantic_request = self.converter.diagnosis_request_from_pb(request)
            
            # Call world model
            pydantic_response = await self.world_model.diagnose(pydantic_request)
            
            # Convert back to protobuf
            return self.converter.diagnosis_response_to_pb(pydantic_response)
            
        except Exception as e:
            # Return error response
            error_response = DiagnosisResponse(
                diagnosis_id=request.diagnosis_id,
                success=False,
                hypotheses=[],
                causal_chain="",
                confidence=0.0,
                explanation=f"Diagnosis failed: {str(e)}"
            )
            return self.converter.diagnosis_response_to_pb(error_response)
    
    async def Manage(self, request: PBManagementRequest, context) -> PBManagementResponse:
        """Handle gRPC Management requests."""
        try:
            pb_response = PBManagementResponse()
            pb_response.request_id = request.request_id
            pb_response.timestamp = datetime.now(timezone.utc).isoformat()
            
            operation = request.operation.lower()
            
            if operation == "health_check":
                health_dict = await self.world_model.get_health_status()
                pb_response.success = True
                pb_response.result = "Health check completed"
                pb_response.health_status.CopyFrom(
                    self.converter.health_status_from_dict(health_dict)
                )
                
            elif operation == "reload_model":
                success = await self.world_model.reload_model()
                pb_response.success = success
                pb_response.result = "Model reloaded" if success else "Model reload failed"
                
            elif operation == "get_metrics":
                health_dict = await self.world_model.get_health_status()
                pb_response.success = True
                pb_response.result = "Metrics retrieved"
                for key, value in health_dict.get("metrics", {}).items():
                    pb_response.metrics[key] = str(value)
                    
            else:
                pb_response.success = False
                pb_response.result = f"Unknown operation: {request.operation}"
            
            return pb_response
            
        except Exception as e:
            pb_response = PBManagementResponse()
            pb_response.request_id = request.request_id
            pb_response.success = False
            pb_response.result = f"Management operation failed: {str(e)}"
            pb_response.timestamp = datetime.now(timezone.utc).isoformat()
            return pb_response