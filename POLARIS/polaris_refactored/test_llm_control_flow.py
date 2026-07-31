#!/usr/bin/env python3
"""
Test script to verify LLM control flow
"""

import sys
import asyncio
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.framework.configuration.builder import ConfigurationBuilder

async def test_llm_control_flow():
    """Test LLM control flow configuration."""
    
    print("=== Testing LLM Control Flow ===")
    
    # Build configuration
    config_builder = ConfigurationBuilder()
    config_builder.add_yaml_source("config/swim_system_config.yaml", priority=100)
    config_builder.add_defaults()
    configuration = config_builder.build()
    
    # Wait for configuration to load
    await configuration.wait_for_load()
    
    # Get control reasoning configuration
    raw_config = configuration.get_raw_config()
    control_config = raw_config.get("control_reasoning", {})
    adaptive_config = control_config.get("adaptive_controller", {})
    
    print(f"Adaptive controller config: {adaptive_config}")
    
    strategy_names = adaptive_config.get("control_strategies", [])
    print(f"Configured control strategies: {strategy_names}")
    
    # Check LLM configuration
    llm_config = raw_config.get("llm", {})
    print(f"LLM provider: {llm_config.get('provider', 'not configured')}")
    print(f"LLM model: {llm_config.get('model_name', 'not configured')}")
    
    # Check agentic LLM reasoning config
    agentic_config = control_config.get("agentic_llm_reasoning", {})
    print(f"Agentic LLM reasoning enabled: {agentic_config.get('enabled', False)}")
    print(f"Max iterations: {agentic_config.get('max_iterations', 'not configured')}")
    
    print("\n=== Expected Flow ===")
    print("1. MonitorAdapter collects SWIM metrics every 10s")
    print("2. TelemetryEvent published to event bus")
    print("3. AdaptiveController processes telemetry")
    print("4. Both strategies evaluate:")
    print("   - ThresholdReactiveStrategy: Rule-based evaluation")
    print("   - LLMControlStrategy: Uses reasoning engine with LLM")
    print("5. Actions generated and AdaptationEvent published")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    asyncio.run(test_llm_control_flow())