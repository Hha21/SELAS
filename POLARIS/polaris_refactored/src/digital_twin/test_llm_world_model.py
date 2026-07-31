"""
Test suite for LLM World Model implementation.

Tests the LLM World Model functionality including system state updates,
behavior prediction, and adaptation impact simulation.
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock

from ..domain.models import SystemState, MetricValue, HealthStatus, AdaptationAction
from ..framework.events import TelemetryEvent
from ..infrastructure.llm import MockLLMClient, LLMConfiguration, LLMProvider, LLMResponse
from .llm_world_model import LLMWorldModel, SystemStateNarrator
from .world_model import PredictionResult, SimulationResult


class TestSystemStateNarrator:
    """Test the SystemStateNarrator component."""
    
    def test_narrate_system_state(self):
        """Test basic system state narration."""
        narrator = SystemStateNarrator()
        
        # Create test system state
        metrics = {
            "cpu_usage": MetricValue("cpu_usage", 75.5, "percent"),
            "memory_usage": MetricValue("memory_usage", 60.2, "percent"),
            "response_time": MetricValue("response_time", 150, "ms")
        }
        
        system_state = SystemState(
            system_id="test_system",
            timestamp=datetime.now(timezone.utc),
            metrics=metrics,
            health_status=HealthStatus.HEALTHY,
            metadata={"environment": "production"}
        )
        
        narrative = narrator.narrate_system_state(system_state)
        
        assert "test_system" in narrative
        assert "healthy" in narrative.lower()
        assert "cpu_usage: 75.5 percent" in narrative
        assert "memory_usage: 60.2 percent" in narrative
        assert "response_time: 150 ms" in narrative
        assert "environment: production" in narrative
    
    def test_narrate_metrics_trend(self):
        """Test metrics trend narration."""
        narrator = SystemStateNarrator()
        
        # Create test metrics history
        metrics_history = [
            {
                "timestamp": "2024-01-01T10:00:00Z",
                "metrics": {
                    "cpu_usage": {"value": 50.0, "unit": "percent"},
                    "memory_usage": {"value": 40.0, "unit": "percent"}
                }
            },
            {
                "timestamp": "2024-01-01T10:05:00Z", 
                "metrics": {
                    "cpu_usage": {"value": 75.0, "unit": "percent"},
                    "memory_usage": {"value": 42.0, "unit": "percent"}
                }
            }
        ]
        
        narrative = narrator.narrate_metrics_trend(metrics_history)
        
        assert "trends" in narrative.lower()
        assert "cpu_usage" in narrative
        assert "increasing" in narrative or "%" in narrative


class TestLLMWorldModel:
    """Test the LLMWorldModel implementation."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        config = LLMConfiguration(
            provider=LLMProvider.MOCK,
            api_endpoint="http://localhost:8000",
            model_name="mock-model"
        )
        return MockLLMClient(config)
    
    @pytest.fixture
    def llm_world_model(self, mock_llm_client):
        """Create LLM World Model instance."""
        return LLMWorldModel(
            llm_client=mock_llm_client,
            conversation_history_limit=5
        )
    
    @pytest.fixture
    def sample_telemetry_event(self):
        """Create sample telemetry event."""
        metrics = {
            "cpu_usage": MetricValue("cpu_usage", 65.0, "percent"),
            "memory_usage": MetricValue("memory_usage", 55.0, "percent"),
            "response_time": MetricValue("response_time", 120, "ms")
        }
        
        system_state = SystemState(
            system_id="web_service",
            timestamp=datetime.now(timezone.utc),
            metrics=metrics,
            health_status=HealthStatus.HEALTHY
        )
        
        return TelemetryEvent(
            event_id="test_event",
            system_state=system_state,
            timestamp=datetime.now(timezone.utc)
        )
    
    @pytest.mark.asyncio
    async def test_update_system_state(self, llm_world_model, sample_telemetry_event):
        """Test system state update functionality."""
        # Update system state
        await llm_world_model.update_system_state(sample_telemetry_event)
        
        # Verify state was stored
        system_id = sample_telemetry_event.system_state.system_id
        assert system_id in llm_world_model.system_states
        assert len(llm_world_model.system_states[system_id]) == 1
        
        # Verify conversation history was updated
        assert system_id in llm_world_model.conversation_history
        assert len(llm_world_model.conversation_history[system_id]) == 1
        
        # Check message content
        message = llm_world_model.conversation_history[system_id][0]
        assert "System state update" in message.content
        assert "web_service" in message.content
        assert message.metadata["type"] == "system_state_update"
    
    @pytest.mark.asyncio
    async def test_predict_system_behavior(self, llm_world_model, sample_telemetry_event):
        """Test behavior prediction functionality."""
        # Setup mock response
        prediction_response = {
            "predictions": {
                "cpu_usage": {
                    "predicted_value": 70.0,
                    "confidence": 0.8,
                    "trend": "increasing",
                    "reasoning": "Current load trend suggests increase"
                }
            },
            "health_prediction": {
                "status": "healthy",
                "confidence": 0.9,
                "reasoning": "System metrics within normal range"
            },
            "overall_confidence": 0.85
        }
        
        llm_world_model.llm_client.set_mock_responses([
            json.dumps(prediction_response)
        ])
        
        # Update system state first
        await llm_world_model.update_system_state(sample_telemetry_event)
        
        # Test prediction
        result = await llm_world_model.predict_system_behavior("web_service", 30)
        
        assert isinstance(result, PredictionResult)
        assert result.probability > 0.0
        assert "cpu_usage_predicted" in result.outcomes
        assert result.outcomes["cpu_usage_predicted"] == 70.0
        assert "predicted_health_status" in result.outcomes
        assert result.outcomes["predicted_health_status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_simulate_adaptation_impact(self, llm_world_model, sample_telemetry_event):
        """Test adaptation impact simulation."""
        # Setup mock response
        simulation_response = {
            "immediate_effects": {
                "metric_changes": {
                    "cpu_usage": {
                        "current_value": 65.0,
                        "predicted_value": 45.0,
                        "change_percentage": -30.8,
                        "confidence": 0.9
                    }
                },
                "system_behavior": "CPU usage should decrease due to scaling"
            },
            "success_probability": 0.85,
            "overall_confidence": 0.8,
            "recommendation": "proceed",
            "reasoning": "Scaling action should reduce system load effectively"
        }
        
        llm_world_model.llm_client.set_mock_responses([
            json.dumps(simulation_response)
        ])
        
        # Update system state first
        await llm_world_model.update_system_state(sample_telemetry_event)
        
        # Create test adaptation action
        action = AdaptationAction(
            action_id="test_action",
            action_type="scale_out",
            target_system="web_service",
            parameters={"scale_factor": 2}
        )
        
        # Test simulation
        result = await llm_world_model.simulate_adaptation_impact("web_service", action)
        
        assert isinstance(result, SimulationResult)
        assert result.probability > 0.0
        assert "immediate_effects" in result.outcomes
        assert "success_probability" in result.outcomes
        assert result.outcomes["success_probability"] == 0.85
        assert result.outcomes["recommendation"] == "proceed"
    
    @pytest.mark.asyncio
    async def test_conversation_history_management(self, llm_world_model, sample_telemetry_event):
        """Test conversation history management."""
        system_id = sample_telemetry_event.system_state.system_id
        
        # Add multiple system state updates
        for i in range(10):
            await llm_world_model.update_system_state(sample_telemetry_event)
        
        # Check history limit is enforced
        history = llm_world_model.get_conversation_history(system_id)
        assert len(history) <= llm_world_model.conversation_history_limit
        
        # Test clearing history
        llm_world_model.clear_conversation_history(system_id)
        history = llm_world_model.get_conversation_history(system_id)
        assert len(history) == 0
    
    def test_get_statistics(self, llm_world_model):
        """Test statistics retrieval."""
        stats = llm_world_model.get_statistics()
        
        assert "total_systems_tracked" in stats
        assert "total_conversation_messages" in stats
        assert "llm_provider" in stats
        assert stats["llm_provider"] == "mock"
        assert "conversation_history_limit" in stats
        assert stats["conversation_history_limit"] == 5
    
    @pytest.mark.asyncio
    async def test_error_handling_in_prediction(self, llm_world_model, sample_telemetry_event):
        """Test error handling in prediction."""
        # Setup mock to return invalid JSON
        llm_world_model.llm_client.set_mock_responses([
            "This is not valid JSON response"
        ])
        
        # Update system state first
        await llm_world_model.update_system_state(sample_telemetry_event)
        
        # Test prediction with invalid response
        result = await llm_world_model.predict_system_behavior("web_service", 30)
        
        assert isinstance(result, PredictionResult)
        assert "prediction_text" in result.outcomes
        assert result.outcomes["prediction_method"] == "text_analysis"
        assert result.probability == 0.3  # Fallback confidence
    
    @pytest.mark.asyncio
    async def test_fallback_model_integration(self, mock_llm_client):
        """Test fallback model integration."""
        # Create mock fallback model
        fallback_model = Mock()
        fallback_model.predict_system_behavior = AsyncMock(
            return_value=PredictionResult({"fallback": True}, 0.6)
        )
        fallback_model.simulate_adaptation_impact = AsyncMock(
            return_value=SimulationResult({"fallback": True}, 0.6)
        )
        
        # Create world model with fallback
        world_model = LLMWorldModel(
            llm_client=mock_llm_client,
            fallback_model=fallback_model
        )
        
        # Force an error by making LLM client fail
        mock_llm_client.generate_response = AsyncMock(
            side_effect=Exception("LLM API error")
        )
        
        # Test prediction fallback
        result = await world_model.predict_system_behavior("test_system", 30)
        assert result.outcomes["fallback"] is True
        assert result.probability == 0.6
        
        # Test simulation fallback
        action = {"action_type": "test", "parameters": {}}
        result = await world_model.simulate_adaptation_impact("test_system", action)
        assert result.outcomes["fallback"] is True
        assert result.probability == 0.6


if __name__ == "__main__":
    # Run basic tests
    async def run_basic_tests():
        """Run basic functionality tests."""
        print("Testing LLM World Model...")
        
        # Test narrator
        narrator = TestSystemStateNarrator()
        narrator.test_narrate_system_state()
        print("✓ System state narration works")
        
        # Test world model
        config = LLMConfiguration(
            provider=LLMProvider.MOCK,
            api_endpoint="http://localhost:8000",
            model_name="mock-model"
        )
        mock_client = MockLLMClient(config)
        world_model = LLMWorldModel(mock_client)
        
        # Test system state update
        metrics = {
            "cpu_usage": MetricValue("cpu_usage", 65.0, "percent")
        }
        system_state = SystemState(
            system_id="test_system",
            timestamp=datetime.now(timezone.utc),
            metrics=metrics,
            health_status=HealthStatus.HEALTHY
        )
        telemetry = TelemetryEvent(
            event_id="test",
            system_state=system_state,
            timestamp=datetime.now(timezone.utc)
        )
        
        await world_model.update_system_state(telemetry)
        print("✓ System state update works")
        
        # Test prediction
        result = await world_model.predict_system_behavior("test_system", 30)
        assert isinstance(result, PredictionResult)
        print("✓ Behavior prediction works")
        
        # Test simulation
        action = {"action_type": "scale_out", "parameters": {"factor": 2}}
        result = await world_model.simulate_adaptation_impact("test_system", action)
        assert isinstance(result, SimulationResult)
        print("✓ Adaptation simulation works")
        
        print("All basic tests passed!")
    
    asyncio.run(run_basic_tests())