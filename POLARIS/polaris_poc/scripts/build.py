#!/usr/bin/env python3
"""
Build script for POLARIS Digital Twin component.

This script handles compilation of Protocol Buffer definitions and
other build tasks for the POLARIS project.
"""

import sys
import subprocess
from pathlib import Path


def run_proto_generation():
    """Run Protocol Buffer stub generation."""
    print("Generating Protocol Buffer stubs...")
    
    script_dir = Path(__file__).parent
    generate_proto_script = script_dir / "generate_proto.py"
    
    try:
        result = subprocess.run([sys.executable, str(generate_proto_script)], check=True)
        print("✓ Protocol Buffer stubs generated successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Protocol Buffer generation failed: {e}")
        return False


def install_dependencies():
    """Install required dependencies."""
    print("Installing dependencies...")
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    requirements_file = project_root / "requirements.txt"
    
    try:
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
        ], cwd=project_root, check=True, capture_output=True, text=True)
        print("✓ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Dependency installation failed: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        return False


def verify_async_test_setup():
    """Verify that async test setup is working."""
    print("Verifying async test setup...")
    
    try:
        import pytest_asyncio
        print(f"✓ pytest-asyncio {pytest_asyncio.__version__} is available")
        return True
    except ImportError:
        print("✗ pytest-asyncio not found - async tests will fail")
        print("  Try: pip install pytest-asyncio")
        return False


def run_basic_tests():
    """Run basic non-async tests first to verify setup."""
    print("Running basic tests...")
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_digital_twin_events.py", 
            "-v", "--tb=short"
        ], cwd=project_root, check=True, capture_output=True, text=True)
        print("✓ Basic tests passed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Basic tests failed: {e}")
        if e.stdout:
            print("stdout:", e.stdout[-500:])  # Last 500 chars
        if e.stderr:
            print("stderr:", e.stderr[-500:])  # Last 500 chars
        return False


def run_tests():
    """Run the full test suite."""
    print("Running full test suite...")
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/", "-v", "--tb=short", "--asyncio-mode=auto"
        ], cwd=project_root, check=True, capture_output=True, text=True)
        print("✓ All tests passed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Tests failed: {e}")
        if e.stdout:
            print("stdout:", e.stdout[-1000:])  # Last 1000 chars
        if e.stderr:
            print("stderr:", e.stderr[-1000:])  # Last 1000 chars
        return False


def main():
    """Main build process."""
    print("POLARIS Digital Twin - Build Script")
    print("=" * 40)
    
    success = True
    
    # Step 0: Install dependencies (optional, can be skipped with --skip-deps)
    if "--skip-deps" not in sys.argv:
        if not install_dependencies():
            success = False
    else:
        print("Skipping dependency installation (--skip-deps specified)")
    
    # Step 0.5: Verify async test setup
    print()
    if not verify_async_test_setup():
        print("Warning: Async test setup issues detected - some tests may fail")
        # Don't fail the build, just warn
    
    # Step 1: Generate Protocol Buffer stubs
    print()
    if not run_proto_generation():
        success = False
    
    # Step 2: Run tests (optional, can be skipped with --skip-tests)
    if "--skip-tests" not in sys.argv:
        print()
        # First run basic tests
        if not run_basic_tests():
            print("Basic tests failed - skipping full test suite")
            success = False
        else:
            # Then run full test suite
            print()
            if not run_tests():
                success = False
    else:
        print("Skipping tests (--skip-tests specified)")
    
    print()
    if success:
        print("✓ Build completed successfully!")
        sys.exit(0)
    else:
        print("✗ Build failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()