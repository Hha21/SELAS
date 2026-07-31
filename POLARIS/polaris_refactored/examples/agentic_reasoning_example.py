"""
Agentic LLM Reasoning Example

Demonstrates how to use the agentic LLM reasoning system with the POLARIS framework.
This example shows the complete integration including tool setup, reasoning execution,
and fallback mechanisms.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timezone
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

from control_reasoning.fallback_reasoning_strategy import create_fallback_reasoning_strategy
from control_reasoning.reasoning_engine import ReasoningContext
from infrastructure.llm.client import OpenAIClient, MockLLMClient
from infrastructure.llm.models import LLMConfiguration, LLMProvider
from digital_twin.world_model import StatisticalWorldModel
from digital_twin.knowledge_base import PolarisKnowledgeBase
from infrastructure.data_storage import InMemoryDataStore
from domain.models import MetricValue, SystemState, HealthStatus


async def main():
    """Main example demonstrating agentic reasoning integration."""
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    logger.info("Starting Agentic LLM Reasoning Example")
    
    # Initialize infrastructure components
    data_store = InMemoryDataStore()
    await data_store.start()
    
    knowledge_base = PolarisKnowledgeBase(data_store)
    world_model = StatisticalWorldModel(knowledge_base)
    
    # Setup sample data
    await setup_sample_data(knowledge_base, world_model)
    
    # Configure LLM client (use MockLLMClient for demo, OpenAIClient for real usage)
    llm_config = LLMConfiguration(
        provider=LLMProvider.MOCK,  # Change to OPENAI for real usage
        api_endpoint="http://localhost:8000",  # Use OpenAI endpoint for real usage
        model_name="mock-model",  # Use "gpt-4" for real usage
        max_tokens=1500,
        temperature=0.1,
        timeout=30.0
    )
    
    llm_client = MockLLMClient(llm_config)
    # For real usage: llm_client = OpenAIClient(llm_config)
    
    # Create fallback reasoning strategy
    reasoning_strategy = create_fallback_reasoning_strategy(
        llm_client=llm_client,
        world_model=world_model,
        knowledge_base=knowledge_base,
        enable_llm_fallback=True,
        llm_confidence_threshold=0.6,
        llm_timeout_seconds=30.0,
        max_llm_retries=2
    )
    
    # Create reasoning scenarios
    scenarios = [
        create_high_cpu_scenario(),
        create_memory_pressure_scenario(),
        create_latency_spike_scenario()
    ]
    
    # Execute reasoning for each scenario
    for i, scenario in enumerate(scenarios, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"SCENARIO {i}: {scenario['name']}")
        logger.info(f"{'='*60}")
        
        try:
            # Execute reasoning
            result = await reasoning_strategy.reason(scenario['context'])
            
            # Display results
            display_reasoning_results(result, logger)
            
            # Show performance statistics
            performance = reasoning_strategy.get_strategy_performance()
            display_performance_stats(performance, logger)
            
        except Exception as e:
            logger.error(f"Reasoning failed for scenario {i}: {str(e)}")
    
    # Cleanup
    await data_store.stop()
    logger.info("\nAgentic LLM Reasoning Example completed")


async def setup_sample_data(knowledge_base: PolarisKnowledgeBase, world_model: StatisticalWorldModel):
    """Setup sample data for the demonstration."""
    
    # Add some sample system states to knowledge base
    sample_states = [
        SystemState(
            system_id="web_service_001",
            timestamp=datetime.now(timezone.utc),
            metrics={
                "cpu_usage": MetricValue("cpu_usage", 45.0, "%"),
                "memory_usage": MetricValue("memory_usage", 60.0, "%"),
                "response_time": MetricValue("response_time", 120.0, "ms")
            },
            health_status=HealthStatus.HEALTHY
        ),
        SystemState(
            system_id="web_service_001", 
            timestamp=datetime.now(timezone.utc),
            metrics={
                "cpu_usage": MetricValue("cpu_usage", 75.0, "%"),
                "memory_usage": MetricValue("memory_usage", 80.0, "%"),
                "response_time": MetricValue("response_time", 200.0, "ms")
            },
            health_status=HealthStatus.WARNING
        )
    ]
    
    for state in sample_states:
        await knowledge_base._states().save(state)
    
    # Add system relationships
    await knowledge_base.add_system_relationship(
        "web_service_001", "database_001", "depends_on", 0.8
    )
    await knowledge_base.add_system_relationship(
        "web_service_001", "cache_001", "depends_on", 0.6
    )


def create_high_cpu_scenario() -> Dict[str, Any]:
    """Create a high CPU usage scenario."""
    
    current_state = {
        "metrics": {
            "cpu_usage": MetricValue("cpu_usage", 92.0, "%"),
            "memory_usage": MetricValue("memory_usage", 65.0, "%"),
            "response_time": MetricValue("response_time", 180.0, "ms"),
            "request_rate": MetricValue("request_rate", 1500.0, "req/min")
        },
        "health_status": HealthStatus.CRITICAL.value,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    historical_data = [
        {"timestamp": "2024-01-01T10:00:00Z", "cpu_usage": 45.0, "memory_usage": 60.0},
        {"timestamp": "2024-01-01T10:05:00Z", "cpu_usage": 65.0, "memory_usage": 62.0},
        {"timestamp": "2024-01-01T10:10:00Z", "cpu_usage": 85.0, "memory_usage": 64.0},
        {"timestamp": "2024-01-01T10:15:00Z", "cpu_usage": 92.0, "memory_usage": 65.0}
    ]
    
    context = ReasoningContext(
        system_id="web_service_001",
        current_state=current_state,
        historical_data=historical_data,
        system_relationships={"dependencies": ["database_001", "cache_001"]}
    )
    
    return {
        "name": "High CPU Usage Crisis",
        "context": context,
        "description": "Web service experiencing critical CPU usage levels"
    }


def create_memory_pressure_scenario() -> Dict[str, Any]:
    """Create a memory pressure scenario."""
    
    current_state = {
        "metrics": {
            "cpu_usage": MetricValue("cpu_usage", 55.0, "%"),
            "memory_usage": MetricValue("memory_usage", 89.0, "%"),
            "response_time": MetricValue("response_time", 250.0, "ms"),
            "gc_frequency": MetricValue("gc_frequency", 15.0, "gc/min")
        },
        "health_status": HealthStatus.WARNING.value,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    historical_data = [
        {"timestamp": "2024-01-01T11:00:00Z", "memory_usage": 70.0, "gc_frequency": 5.0},
        {"timestamp": "2024-01-01T11:05:00Z", "memory_usage": 75.0, "gc_frequency": 8.0},
        {"timestamp": "2024-01-01T11:10:00Z", "memory_usage": 82.0, "gc_frequency": 12.0},
        {"timestamp": "2024-01-01T11:15:00Z", "memory_usage": 89.0, "gc_frequency": 15.0}
    ]
    
    context = ReasoningContext(
        system_id="api_service_002",
        current_state=current_state,
        historical_data=historical_data,
        system_relationships={"dependencies": ["message_queue", "redis_cache"]}
    )
    
    return {
        "name": "Memory Pressure Building",
        "context": context,
        "description": "API service showing increasing memory pressure and GC activity"
    }


def create_latency_spike_scenario() -> Dict[str, Any]:
    """Create a latency spike scenario."""
    
    current_state = {
        "metrics": {
            "cpu_usage": MetricValue("cpu_usage", 40.0, "%"),
            "memory_usage": MetricValue("memory_usage", 55.0, "%"),
            "response_time": MetricValue("response_time", 2500.0, "ms"),
            "error_rate": MetricValue("error_rate", 5.2, "%")
        },
        "health_status": HealthStatus.WARNING.value,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    historical_data = [
        {"timestamp": "2024-01-01T12:00:00Z", "response_time": 120.0, "error_rate": 0.1},
        {"timestamp": "2024-01-01T12:05:00Z", "response_time": 150.0, "error_rate": 0.3},
        {"timestamp": "2024-01-01T12:10:00Z", "response_time": 800.0, "error_rate": 2.1},
        {"timestamp": "2024-01-01T12:15:00Z", "response_time": 2500.0, "error_rate": 5.2}
    ]
    
    context = ReasoningContext(
        system_id="payment_service_003",
        current_state=current_state,
        historical_data=historical_data,
        system_relationships={"dependencies": ["payment_gateway", "fraud_detection"]}
    )
    
    return {
        "name": "Sudden Latency Spike",
        "context": context,
        "description": "Payment service experiencing sudden latency increase with rising errors"
    }


def display_reasoning_results(result, logger):
    """Display the reasoning results in a formatted way."""
    
    logger.info(f"Reasoning Confidence: {result.confidence:.2f}")
    
    logger.info("\nInsights:")
    for i, insight in enumerate(result.insights, 1):
        if isinstance(insight, dict):
            insight_type = insight.get("type", "unknown")
            logger.info(f"  {i}. [{insight_type}] {insight}")
        else:
            logger.info(f"  {i}. {insight}")
    
    logger.info(f"\nRecommendations ({len(result.recommendations)}):")
    for i, rec in enumerate(result.recommendations, 1):
        if isinstance(rec, dict):
            action_type = rec.get("action_type", "unknown")
            parameters = rec.get("parameters", {})
            source = rec.get("source", "unknown")
            logger.info(f"  {i}. Action: {action_type}")
            logger.info(f"     Parameters: {parameters}")
            logger.info(f"     Source: {source}")
        else:
            logger.info(f"  {i}. {rec}")


def display_performance_stats(performance, logger):
    """Display strategy performance statistics."""
    
    logger.info("\nStrategy Performance:")
    for strategy_name, stats in performance.items():
        logger.info(f"  {strategy_name}:")
        logger.info(f"    Attempts: {stats['attempts']}")
        logger.info(f"    Success Rate: {stats['success_rate']:.2f}")
        logger.info(f"    Avg Confidence: {stats['average_confidence']:.2f}")
        logger.info(f"    Reliability Score: {stats['reliability_score']:.2f}")


if __name__ == "__main__":
    asyncio.run(main())