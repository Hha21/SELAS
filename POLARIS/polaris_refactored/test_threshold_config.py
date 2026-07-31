#!/usr/bin/env python3
"""
Test script to verify threshold configuration loading
"""

import sys
import asyncio
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.framework.configuration.builder import ConfigurationBuilder

async def test_threshold_config():
    """Test threshold configuration loading."""
    
    print("=== Testing Threshold Configuration ===")
    
    # Build configuration
    config_builder = ConfigurationBuilder()
    config_builder.add_yaml_source("config/swim_system_config.yaml", priority=100)
    config_builder.add_defaults()
    configuration = config_builder.build()
    
    # Wait for configuration to load
    await configuration.wait_for_load()
    
    # Get raw configuration
    raw_config = configuration.get_raw_config()
    
    # Check control reasoning configuration
    control_config = raw_config.get("control_reasoning", {})
    print(f"Control reasoning config keys: {list(control_config.keys())}")
    
    threshold_config = control_config.get("threshold_reactive", {})
    print(f"Threshold reactive config keys: {list(threshold_config.keys())}")
    
    rules = threshold_config.get("rules", [])
    print(f"Found {len(rules)} threshold rules:")
    
    for i, rule in enumerate(rules):
        print(f"  Rule {i+1}: {rule.get('rule_id', 'unknown')}")
        print(f"    Name: {rule.get('name', 'N/A')}")
        print(f"    Enabled: {rule.get('enabled', False)}")
        print(f"    Action: {rule.get('action_type', 'N/A')}")
        print(f"    Conditions: {len(rule.get('conditions', []))}")
        
        for j, condition in enumerate(rule.get('conditions', [])):
            print(f"      Condition {j+1}: {condition.get('metric_name')} {condition.get('operator')} {condition.get('value')}")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    asyncio.run(test_threshold_config())