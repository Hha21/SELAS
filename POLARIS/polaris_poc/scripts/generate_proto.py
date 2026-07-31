#!/usr/bin/env python3
"""
Script to generate Python gRPC stubs from Protocol Buffer definitions.

This script compiles the .proto files into Python modules for use
with the POLARIS Digital Twin gRPC services.
"""

import re
import subprocess
import sys
from pathlib import Path


def generate_grpc_stubs():
    """Generate Python gRPC stubs from proto files."""
    
    # Get the project root directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    proto_dir = project_root / "src" / "polaris" / "proto"
    
    # Ensure proto directory exists
    if not proto_dir.exists():
        print(f"Error: Proto directory not found: {proto_dir}")
        return False
    
    # Find all .proto files
    proto_files = list(proto_dir.glob("*.proto"))
    if not proto_files:
        print(f"No .proto files found in {proto_dir}")
        return False
    
    print(f"Found {len(proto_files)} proto file(s):")
    for proto_file in proto_files:
        print(f"  - {proto_file.name}")
    
    # Generate Python stubs for each proto file
    success = True
    for proto_file in proto_files:
        print(f"\nGenerating stubs for {proto_file.name}...")
        
        # Build the protoc command
        cmd = [
            sys.executable, "-m", "grpc_tools.protoc",
            f"--proto_path={proto_dir}",
            f"--python_out={proto_dir}",
            f"--grpc_python_out={proto_dir}",
            str(proto_file)
        ]
        
        try:
            # Run protoc
            result = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                text=True,
                check=True
            )
            
            print(f"✓ Successfully generated stubs for {proto_file.name}")
            
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to generate stubs for {proto_file.name}")
            print(f"Error: {e.stderr}")
            success = False
        except FileNotFoundError:
            print("✗ grpc_tools.protoc not found. Please install grpcio-tools:")
            print("  pip install grpcio-tools")
            return False
    
    if success:
        print("\n✓ All gRPC stubs generated successfully!")
        
        # List generated files
        generated_files = list(proto_dir.glob("*_pb2.py")) + list(proto_dir.glob("*_pb2_grpc.py"))
        if generated_files:
            print("\nPost-processing generated files to fix imports...")
            for gen_file in generated_files:
                text = gen_file.read_text()
                text = re.sub(r"^import (\w+_pb2) as (\w+)$", r"from . import \1 as \2", text, flags=re.M)
                text = re.sub(r"^from (\w+_pb2) import (.+)$", r"from .\1 import \2", text, flags=re.M)
                gen_file.write_text(text)

            print("\nGenerated files:")
            for gen_file in generated_files:
                print(f"  - {gen_file.name}")
    else:
        print("\n✗ Some stub generation failed. Check errors above.")
    
    return success


def main():
    """Main entry point."""
    print("POLARIS Digital Twin - gRPC Stub Generator")
    print("=" * 50)
    
    success = generate_grpc_stubs()
    
    if success:
        print("\nStub generation completed successfully!")
        sys.exit(0)
    else:
        print("\nStub generation failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()