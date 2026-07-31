"""
Integration test for fallback reasoning strategy.

This test demonstrates and tests the fallback mechanisms between
LLM-based agentic reasoning and traditional statistical/causal strategies.
"""

import asyncio
import logging
from typing import Dict, Any
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src'))

from control_reasoning.fallback_reasoning_strategy import FallbackReasoningStrategy
from control_reasoning.reasoning_engine import ReasoningContext
from infrastructure.llm.client import MockLLMClient
from infrastructure.llm.models import LLMConfiguration, LLMProvider
from infrastructure.llm.exceptions import LLMAPIError, LLMTimeoutError
from digital_twin.world_model import StatisticalWorldModel
from digital_twin.knowledge_base import PolarisKnowledgeBase
from infrastructure.data_storage import InMemoryDataStore
from domain.models import MetricValue, SystemState, HealthStatus


async def test_fallback_integration():
    """Test the fallback integration between different reasoning strategies."""
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("Starting fallback integration test")
    
    # Create mock components
    data_store = InMemoryDataStore()
    await data_store.start()
    
    knowledge_base = PolarisKnowledgeBase(data_store)
    world_model = StatisticalWorldModel(knowledge_base)
    
    # Create LLM client configuration
    llm_config = LLMConfiguration(
        provider=LLMProvider.MOCK,
        api_endpoint="http://localhost:8000",
        model_name="mock-model",
        max_tokens=1000,
        temperature=0.1
    )
    
    # Test scenarios
    test_scenarios = [
        {
            "name": "Normal LLM Operation",
            "llm_client": MockLLMClient(llm_config),
            "expected_strategy": "agentic_llm"
        },
        {
            "name": "LLM API Error Fallback",
            "llm_client": FailingMockLLMClient(llm_config, fail_with=LLMAPIError("API Error")),
            "expected_strategy": "causal"
        },
        {
            "name": "LLM Timeout Fallback",
            "llm_client": FailingMockLLMClient(llm_config, fail_with=LLMTimeoutError("Timeout")),
            "expected_strategy": "causal"
        }
    ]
    
    # Create test context
    test_context = create_test_context()
    
    for scenario in test_scenarios:
        logger.info(f"\n--- Testing: {scenario['name']} ---")
        
        # Create fallback strategy
        fallback_strategy = FallbackReasoningStrategy(
            llm_client=scenario["llm_client"],
            world_model=world_model,
            knowledge_base=knowledge_base,
            llm_timeout_seconds=5.0,
            max_llm_retries=1
        )
        
        try:
            # Execute reasoning
            result = await fallback_strategy.reason(test_context)
            
            # Analyze result
            logger.info(f"Reasoning completed with confidence: {result.confidence}")
            logger.info(f"Number of insights: {len(result.insights)}")
            logger.info(f"Number of recommendations: {len(result.recommendations)}")
            
            # Check which strategy was used
            strategy_used = None
            for insight in result.insights:
                if isinstance(insight, dict) and insight.get("type") == "fallback_strategy_info":
                    strategy_used = insight.get("strategy_used")
                    break
            
            if strategy_used:
                logger.info(f"Strategy used: {strategy_used}")
                if strategy_used == scenario["expected_strategy"]:
                    logger.info("✓ Expected strategy was used")
                else:
                    logger.warning(f"✗ Expected {scenario['expected_strategy']}, got {strategy_used}")
            else:
                logger.warning("✗ Could not determine which strategy was used")
            
            # Show performance stats
            performance = fallback_strategy.get_strategy_performance()
            logger.info("Strategy Performance:")
            for strategy_name, stats in performance.items():
                logger.info(f"  {strategy_name}: {stats['attempts']} attempts, "
                          f"{stats['success_rate']:.2f} success rate, "
                          f"{stats['reliability_score']:.2f} reliability")
            
        except Exception as e:
            logger.error(f"Test failed with error: {str(e)}")
    
    await data_store.stop()
    logger.info("\nFallback integration test completed")


def create_test_context() -> ReasoningContext:
    """Create a test reasoning context with sample data."""
    
    # Create sample metrics
    metrics = {
        "cpu_usage": MetricValue(name="cpu_usage", value=85.0, unit="%"),
        "memory_usage": MetricValue(name="memory_usage", value=70.0, unit="%"),
        "response_time": MetricValue(name="response_time", value=150.0, unit="ms")
    }
    
    # Create current state
    current_state = {
        "metrics": metrics,
        "health_status": HealthStatus.WARNING.value,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # Create historical data (simplified)
    historical_data = [
        {"timestamp": "2024-01-01T10:00:00Z", "cpu_usage": 60.0},
        {"timestamp": "2024-01-01T10:05:00Z", "cpu_usage": 65.0},
        {"timestamp": "2024-01-01T10:10:00Z", "cpu_usage": 80.0}
    ]
    
    return ReasoningContext(
        system_id="test_system_001",
        current_state=current_state,
        historical_data=historical_data,
        system_relationships={"dependencies": ["database", "cache"]}
    )


class FailingMockLLMClient(MockLLMClient):
    """Mock LLM client that fails with specified exceptions for testing."""
    
    def __init__(self, config, fail_with: Exception):
        super().__init__(config)
        self.fail_with = fail_with
    
    async def generate_response(self, request):
        """Always fail with the specified exception."""
        raise self.fail_with


if __name__ == "__main__":
    asyncio.run(test_fallback_integration())