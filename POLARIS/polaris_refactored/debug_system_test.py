#!/usr/bin/env python3
"""
Debug version of complete system test with detailed logging
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from run_swim_system import SwimSystemRunner


async def debug_system_test():
    """Debug version with detailed logging to identify issues."""
    
    print("=== Debug System Test ===")
    
    # Set environment for testing
    os.environ["POLARIS_LLM__PROVIDER"] = "mock"
    os.environ["POLARIS_METRICS_INTERVAL"] = "3"  # Very short for testing
    
    # Clean up any existing metrics log
    metrics_log_path = "./logs/polaris_metrics.log"
    if os.path.exists(metrics_log_path):
        os.remove(metrics_log_path)
        print(f"✓ Cleaned up existing metrics log: {metrics_log_path}")
    
    # Create runner
    runner = SwimSystemRunner()
    
    print(f"Metrics interval: {runner.metrics_interval}s")
    print(f"Metrics log path: {runner.metrics_log_path}")
    
    try:
        print("\n--- Setting up framework ---")
        await runner.setup_framework()
        
        print("✓ Framework setup completed")
        
        # Check if configuration loaded correctly
        if runner.framework and runner.framework.configuration:
            config = runner.framework.configuration
            try:
                framework_config = config.get_framework_config()
                print(f"Logging format from loaded config: {framework_config.logging_config.format}")
                print(f"Logging level from loaded config: {framework_config.logging_config.level}")
                print(f"Logging output from loaded config: {framework_config.logging_config.output}")
            except Exception as e:
                print(f"✗ Failed to get framework config: {e}")
        
        print("\n--- Starting framework ---")
        await runner.framework.start()
        print("✓ Framework started")
        
        print("\n--- Starting metrics worker ---")
        try:
            await runner._ensure_metrics_log_dir()
            runner._metrics_task = asyncio.create_task(runner._metrics_worker())
            print("✓ Metrics worker started")
        except Exception as e:
            print(f"✗ Failed to start metrics worker: {e}")
        
        print(f"\n--- Running for 10 seconds (metrics every {runner.metrics_interval}s) ---")
        
        # Let it run for 10 seconds
        for i in range(10):
            await asyncio.sleep(1)
            print(f"Running... {i+1}/10s", end='\r')
            
            # Check if metrics file exists
            if os.path.exists(metrics_log_path):
                file_size = os.path.getsize(metrics_log_path)
                if file_size > 0:
                    print(f"\n✓ Metrics file created! Size: {file_size} bytes")
                    break
        
        print(f"\n--- Stopping system ---")
        runner._shutdown_event.set()
        
        # Wait a bit for final metrics write
        await asyncio.sleep(2)
        
        await runner.stop_system()
        
    except Exception as e:
        print(f"✗ System error: {e}")
        import traceback
        traceback.print_exc()
        await runner.stop_system()
    
    print("\n--- Final Results ---")
    
    # Check metrics log
    if os.path.exists(metrics_log_path):
        file_size = os.path.getsize(metrics_log_path)
        print(f"✓ Metrics log exists: {metrics_log_path} ({file_size} bytes)")
        
        if file_size > 0:
            with open(metrics_log_path, 'r') as f:
                lines = f.readlines()
            
            print(f"Number of metrics entries: {len(lines)}")
            
            if lines:
                print("\nFirst entry (truncated):")
                print(lines[0][:200] + "..." if len(lines[0]) > 200 else lines[0])
        else:
            print("✗ Metrics log file is empty")
    else:
        print("✗ Metrics log file was not created")
    
    # Check logs directory
    logs_dir = Path("./logs")
    if logs_dir.exists():
        print(f"\nLogs directory contents:")
        for file in logs_dir.iterdir():
            if file.is_file():
                size = file.stat().st_size
                print(f"  {file.name}: {size} bytes")
    
    print("\n=== Debug Test Completed ===")


if __name__ == "__main__":
    asyncio.run(debug_system_test())