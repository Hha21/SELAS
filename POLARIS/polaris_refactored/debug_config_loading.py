#!/usr/bin/env python3
"""
Debug configuration loading to see why format is not being set correctly
"""

import asyncio
import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.framework.configuration.builder import ConfigurationBuilder


async def debug_config_loading():
    """Debug the configuration loading process."""
    
    print("=== Debug Configuration Loading ===")
    
    # Create builder
    config_builder = ConfigurationBuilder()
    
    # Add YAML source first
    print("1. Adding YAML source...")
    config_builder.add_yaml_source("config/swim_system_config.yaml", priority=100)
    
    # Check sources before adding defaults
    print(f"Sources after YAML: {len(config_builder.sources)}")
    for i, source in enumerate(config_builder.sources):
        print(f"  Source {i}: priority={source.get_priority()}, type={type(source).__name__}")
    
    # Add defaults
    print("\n2. Adding defaults...")
    config_builder.add_defaults()
    
    # Check sources after adding defaults
    print(f"Sources after defaults: {len(config_builder.sources)}")
    for i, source in enumerate(config_builder.sources):
        print(f"  Source {i}: priority={source.get_priority()}, type={type(source).__name__}")
    
    # Build configuration
    print("\n3. Building configuration...")
    configuration = config_builder.build()
    
    # Wait for configuration to load
    print("4. Waiting for configuration to load...")
    await configuration.wait_for_load()
    
    # Check the loaded configuration
    print("\n5. Checking loaded configuration...")
    try:
        framework_config = configuration.get_framework_config()
        print(f"Logging level: {framework_config.logging_config.level}")
        print(f"Logging format: {framework_config.logging_config.format}")
        print(f"Logging output: {framework_config.logging_config.output}")
        
        # Check raw configuration data
        print("\n6. Checking raw configuration data...")
        raw_config = configuration._config_data
        if 'framework' in raw_config and 'logging_config' in raw_config['framework']:
            logging_config = raw_config['framework']['logging_config']
            print(f"Raw logging config: {logging_config}")
        else:
            print("No logging_config found in raw data")
            
    except Exception as e:
        print(f"Error getting framework config: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n=== Debug Completed ===")


if __name__ == "__main__":
    asyncio.run(debug_config_loading())