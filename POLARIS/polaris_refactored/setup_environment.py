#!/usr/bin/env python3
"""
POLARIS Environment Setup Script

Sets up the environment for running the POLARIS framework with SWIM.
"""

import os
import sys
from pathlib import Path


def setup_python_path():
    """Add src directory to Python path."""
    src_path = Path(__file__).parent / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    print(f"Added {src_path} to Python path")


def check_dependencies():
    """Check if required dependencies are available."""
    required_packages = [
        "pydantic",
        "asyncio",
        "dataclasses",
        "typing",
        "datetime",
        "pathlib",
        "logging",
        "json",
        "yaml"
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"Missing packages: {missing_packages}")
        print("Please install them using: pip install " + " ".join(missing_packages))
        return False
    
    print("All required packages are available")
    return True


def create_directories():
    """Create necessary directories."""
    directories = [
        "logs",
        "data",
        "config/prompts"
    ]
    
    for directory in directories:
        dir_path = Path(__file__).parent / directory
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"Created directory: {dir_path}")


def check_swim_availability():
    """Check if SWIM is available."""
    import socket
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 4242))
        sock.close()
        
        if result == 0:
            print("✓ SWIM is available on localhost:4242")
            return True
        else:
            print("✗ SWIM is not available on localhost:4242")
            print("Please start SWIM before running the system")
            return False
    except Exception as e:
        print(f"✗ Error checking SWIM availability: {e}")
        return False


def check_environment_variables():
    """Check environment variables."""
    print("\nEnvironment Variables:")
    
    # Check Google AI API key
    google_key = os.getenv("GOOGLE_AI_API_KEY")
    if google_key:
        print(f"✓ GOOGLE_AI_API_KEY is set (length: {len(google_key)})")
    else:
        print("✗ GOOGLE_AI_API_KEY is not set")
        print("  Get your API key from: https://makersuite.google.com/app/apikey")
        print("  Set it with: export GOOGLE_AI_API_KEY='your-api-key-here'")
    
    # Check other optional environment variables
    optional_vars = [
        "POLARIS_LOG_LEVEL",
        "POLARIS_FRAMEWORK__ENVIRONMENT",
        "POLARIS_LLM__PROVIDER"
    ]
    
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            print(f"✓ {var} = {value}")
        else:
            print(f"  {var} not set (optional)")


def main():
    """Main setup function."""
    print("POLARIS Environment Setup")
    print("=" * 50)
    
    # Setup Python path
    setup_python_path()
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Create directories
    create_directories()
    
    # Check SWIM availability
    swim_available = check_swim_availability()
    
    # Check environment variables
    check_environment_variables()
    
    print("\n" + "=" * 50)
    print("Setup Summary:")
    print("✓ Python path configured")
    print("✓ Dependencies checked")
    print("✓ Directories created")
    
    if swim_available:
        print("✓ SWIM is available")
    else:
        print("✗ SWIM is not available")
    
    google_key = os.getenv("GOOGLE_AI_API_KEY")
    if google_key:
        print("✓ Google AI API key is set")
    else:
        print("✗ Google AI API key is not set")
    
    print("\nNext steps:")
    if not swim_available:
        print("1. Start SWIM on localhost:4242")
    if not google_key:
        print("2. Set GOOGLE_AI_API_KEY environment variable")
    print("3. Run: python run_swim_system.py")


if __name__ == "__main__":
    main()