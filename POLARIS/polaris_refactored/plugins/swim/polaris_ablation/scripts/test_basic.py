#!/usr/bin/env python3
"""
Basic Test Script for SWIM POLARIS Adaptation System

Simple test to verify basic functionality without full POLARIS framework.
"""

import asyncio
import sys
import logging
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

async def test_basic_functionality():
    """Test basic system functionality."""
    print("Testing basic SWIM POLARIS functionality...")
    
    try:
        # Test imports
        print("Testing imports...")
        from swim_driver import SwimPolarisDriver, SystemStatus
        print("✓ swim_driver imported successfully")
        
        # Test configuration loading
        print("Testing configuration...")
        config_file = Path(__file__).parent.parent / "config" / "base_config.yaml"
        
        if not config_file.exists():
            print(f"✗ Configuration file not found: {config_file}")
            print("Please run setup_environment.py first")
            return False
        
        # Create driver
        print("Creating driver...")
        driver = SwimPolarisDriver(str(config_file))
        print("✓ Driver created successfully")
        
        # Test initialization
        print("Testing initialization...")
        success = await driver.initialize()
        
        if success:
            print("✓ System initialized successfully")
            
            # Test status
            status = await driver.get_status()
            print(f"✓ System status: {status.health_status.value}")
            
            # Test shutdown
            await driver.shutdown()
            print("✓ System shutdown successfully")
            
            return True
        else:
            print("✗ System initialization failed")
            return False
    
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_swim_connection():
    """Test SWIM connection."""
    print("\nTesting SWIM connection...")
    
    try:
        # Import SWIM connector using dynamic loading
        connector_path = Path(__file__).parent.parent.parent / "connector.py"
        
        if not connector_path.exists():
            print(f"✗ SWIM connector not found at: {connector_path}")
            return False
        
        import importlib.util
        spec = importlib.util.spec_from_file_location("swim_connector", connector_path)
        connector_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(connector_module)
        
        SwimTCPConnector = connector_module.SwimTCPConnector
        
        # Test with default config
        swim_config = {
            "connection": {
                "host": "localhost",
                "port": 4242
            },
            "implementation": {
                "timeout": 5.0,
                "max_retries": 1
            }
        }
        
        connector = SwimTCPConnector(swim_config)
        print("✓ SWIM connector created")
        
        # Test connection (this will fail if SWIM is not running)
        try:
            connected = await connector.connect()
            if connected:
                print("✓ SWIM connection successful")
                
                # Test basic commands
                system_state = await connector.get_system_state()
                print(f"✓ SWIM system state retrieved: {system_state.health_status.value}")
                
                await connector.disconnect()
                print("✓ SWIM disconnection successful")
                
                return True
            else:
                print("⚠ SWIM connection failed (SWIM may not be running)")
                return False
        
        except Exception as e:
            print(f"⚠ SWIM connection test failed: {e}")
            print("  This is expected if SWIM is not running")
            return False
    
    except Exception as e:
        print(f"✗ SWIM connector test failed: {e}")
        return False

def main():
    """Main test function."""
    print("SWIM POLARIS Basic Functionality Test")
    print("=" * 50)
    
    # Setup logging
    logging.basicConfig(level=logging.WARNING)  # Reduce noise
    
    async def run_tests():
        success = True
        
        # Test basic functionality
        if not await test_basic_functionality():
            success = False
        
        # Test SWIM connection
        if not await test_swim_connection():
            print("Note: SWIM connection test failed, but this is expected if SWIM is not running")
        
        print("\n" + "=" * 50)
        if success:
            print("✓ Basic tests completed successfully")
            print("\nNext steps:")
            print("1. Start SWIM system if you want to test full functionality")
            print("2. Run: python scripts/start_system.py --config config/base_config.yaml")
            return 0
        else:
            print("✗ Some tests failed")
            return 1
    
    return asyncio.run(run_tests())

if __name__ == "__main__":
    sys.exit(main())