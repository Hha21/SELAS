#!/usr/bin/env python3
"""
Test script to verify SWIM connection and metric collection
"""

import sys
import asyncio
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from plugins.swim.connector import SwimTCPConnector

async def test_swim_connection():
    """Test SWIM connection and metric collection."""
    
    print("=== Testing SWIM Connection ===")
    
    # Create SWIM connector with default config
    swim_config = {
        "connection": {
            "host": "localhost",
            "port": 4242
        },
        "implementation": {
            "timeout": 30.0,
            "max_retries": 3
        }
    }
    
    connector = SwimTCPConnector(swim_config)
    
    try:
        # Test connection
        print("Testing connection to SWIM...")
        connected = await connector.connect()
        
        if not connected:
            print("❌ Failed to connect to SWIM")
            print("Make sure SWIM is running on localhost:4242")
            return
        
        print("✅ Connected to SWIM successfully")
        
        # Test metric collection
        print("\nCollecting metrics...")
        metrics = await connector.collect_metrics()
        
        if not metrics:
            print("❌ No metrics collected")
            return
        
        print("✅ Metrics collected successfully:")
        for name, metric in metrics.items():
            print(f"  - {name}: {metric.value} {metric.unit}")
        
        # Test system state
        print("\nGetting system state...")
        system_state = await connector.get_system_state()
        print(f"✅ System state: {system_state.health_status.value}")
        print(f"   Metrics count: {len(system_state.metrics)}")
        
        # Disconnect
        await connector.disconnect()
        print("\n✅ Disconnected successfully")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    asyncio.run(test_swim_connection())