#!/usr/bin/env python3
"""
Setup script for POLARIS Digital Twin test environment.

This script ensures the test environment is properly configured
with all necessary dependencies and configurations.
"""

import sys
import subprocess
from pathlib import Path


def check_python_version():
    """Check if Python version is compatible."""
    print("Checking Python version...")
    
    if sys.version_info < (3, 8):
        print(f"✗ Python 3.8+ required, found {sys.version}")
        return False
    
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True


def install_requirements():
    """Install requirements from requirements.txt."""
    print("Installing requirements...")
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    requirements_file = project_root / "requirements.txt"
    
    if not requirements_file.exists():
        print(f"✗ Requirements file not found: {requirements_file}")
        return False
    
    try:
        subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
        ], check=True, capture_output=True, text=True)
        print("✓ Requirements installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install requirements: {e}")
        if e.stderr:
            print(f"Error: {e.stderr}")
        return False


def verify_pytest_asyncio():
    """Verify pytest-asyncio is properly installed."""
    print("Verifying pytest-asyncio installation...")
    
    try:
        import pytest_asyncio
        print(f"✓ pytest-asyncio {pytest_asyncio.__version__} installed")
        return True
    except ImportError:
        print("✗ pytest-asyncio not found")
        return False


def verify_grpc_tools():
    """Verify grpcio-tools is properly installed."""
    print("Verifying grpcio-tools installation...")
    
    try:
        import grpc_tools
        print("✓ grpcio-tools installed")
        return True
    except ImportError:
        print("✗ grpcio-tools not found")
        return False


def run_simple_test():
    """Run a simple test to verify the setup."""
    print("Running simple test...")
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    try:
        # Run just the non-async tests first
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_digital_twin_events.py::TestKnowledgeEvent::test_knowledge_event_validation",
            "-v"
        ], cwd=project_root, check=True, capture_output=True, text=True)
        print("✓ Simple test passed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Simple test failed: {e}")
        if e.stdout:
            print(f"stdout: {e.stdout}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
        return False


def main():
    """Main setup process."""
    print("POLARIS Digital Twin - Test Environment Setup")
    print("=" * 50)
    
    success = True
    
    # Check Python version
    if not check_python_version():
        success = False
    
    print()
    
    # Install requirements
    if not install_requirements():
        success = False
    
    print()
    
    # Verify key dependencies
    if not verify_pytest_asyncio():
        success = False
    
    print()
    
    if not verify_grpc_tools():
        success = False
    
    print()
    
    # Run simple test
    if success and not run_simple_test():
        success = False
    
    print()
    if success:
        print("✓ Test environment setup completed successfully!")
        print("You can now run tests with: python -m pytest tests/ -v")
        sys.exit(0)
    else:
        print("✗ Test environment setup failed!")
        print("Please check the errors above and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()