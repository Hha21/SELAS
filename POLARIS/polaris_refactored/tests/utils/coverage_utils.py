"""
Coverage utilities for POLARIS unit testing framework.

This module provides utilities for measuring and reporting test coverage
to ensure the 80% minimum coverage requirement is met.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json


class CoverageAnalyzer:
    """Analyzes test coverage and provides detailed reporting."""
    
    def __init__(self, source_dir: str = "src", test_dir: str = "tests"):
        self.source_dir = Path(source_dir)
        self.test_dir = Path(test_dir)
        self.coverage_threshold = 80.0
        
    def run_coverage_analysis(self, test_pattern: str = "test_*.py") -> Dict[str, float]:
        """Run coverage analysis and return coverage percentages by module."""
        try:
            # Run pytest with coverage
            cmd = [
                sys.executable, "-m", "pytest",
                f"--cov={self.source_dir}",
                "--cov-report=json",
                "--cov-report=term-missing",
                f"{self.test_dir}/{test_pattern}"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=".")
            
            if result.returncode != 0:
                print(f"Coverage analysis failed: {result.stderr}")
                return {}
            
            # Parse coverage JSON report
            coverage_file = Path("coverage.json")
            if coverage_file.exists():
                with open(coverage_file, 'r') as f:
                    coverage_data = json.load(f)
                
                return self._parse_coverage_data(coverage_data)
            
        except Exception as e:
            print(f"Error running coverage analysis: {e}")
            return {}
        
        return {}
    
    def _parse_coverage_data(self, coverage_data: Dict) -> Dict[str, float]:
        """Parse coverage data and extract module-level coverage."""
        module_coverage = {}
        
        files = coverage_data.get("files", {})
        for file_path, file_data in files.items():
            # Convert file path to module name
            if file_path.startswith(str(self.source_dir)):
                relative_path = Path(file_path).relative_to(self.source_dir)
                module_name = str(relative_path).replace("/", ".").replace("\\", ".").replace(".py", "")
                
                summary = file_data.get("summary", {})
                covered_lines = summary.get("covered_lines", 0)
                num_statements = summary.get("num_statements", 1)
                
                coverage_percent = (covered_lines / num_statements) * 100 if num_statements > 0 else 0
                module_coverage[module_name] = coverage_percent
        
        return module_coverage
    
    def generate_coverage_report(self, module_coverage: Dict[str, float]) -> str:
        """Generate a detailed coverage report."""
        report_lines = [
            "POLARIS Test Coverage Report",
            "=" * 50,
            ""
        ]
        
        total_coverage = sum(module_coverage.values()) / len(module_coverage) if module_coverage else 0
        
        report_lines.extend([
            f"Overall Coverage: {total_coverage:.2f}%",
            f"Coverage Threshold: {self.coverage_threshold}%",
            f"Status: {'PASS' if total_coverage >= self.coverage_threshold else 'FAIL'}",
            "",
            "Module Coverage Details:",
            "-" * 30
        ])
        
        # Sort modules by coverage percentage
        sorted_modules = sorted(module_coverage.items(), key=lambda x: x[1], reverse=True)
        
        for module_name, coverage in sorted_modules:
            status = "✓" if coverage >= self.coverage_threshold else "✗"
            report_lines.append(f"{status} {module_name:<40} {coverage:>6.2f}%")
        
        # Identify modules that need attention
        low_coverage_modules = [
            (module, coverage) for module, coverage in module_coverage.items()
            if coverage < self.coverage_threshold
        ]
        
        if low_coverage_modules:
            report_lines.extend([
                "",
                "Modules Below Threshold:",
                "-" * 25
            ])
            
            for module, coverage in sorted(low_coverage_modules, key=lambda x: x[1]):
                needed = self.coverage_threshold - coverage
                report_lines.append(f"• {module}: {coverage:.2f}% (need +{needed:.2f}%)")
        
        return "\n".join(report_lines)
    
    def identify_untested_files(self) -> List[str]:
        """Identify source files that have no corresponding test files."""
        untested_files = []
        
        for py_file in self.source_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
                
            # Convert source file path to expected test file path
            relative_path = py_file.relative_to(self.source_dir)
            test_file_name = f"test_{py_file.stem}.py"
            
            # Check multiple possible test locations
            possible_test_paths = [
                self.test_dir / "unit" / relative_path.parent / test_file_name,
                self.test_dir / "integration" / relative_path.parent / test_file_name,
                self.test_dir / test_file_name
            ]
            
            if not any(test_path.exists() for test_path in possible_test_paths):
                untested_files.append(str(relative_path))
        
        return untested_files
    
    def suggest_test_improvements(self, module_coverage: Dict[str, float]) -> List[str]:
        """Suggest improvements to increase test coverage."""
        suggestions = []
        
        # Identify modules with low coverage
        low_coverage = [
            (module, coverage) for module, coverage in module_coverage.items()
            if coverage < self.coverage_threshold
        ]
        
        if low_coverage:
            suggestions.append("Focus on improving coverage for these modules:")
            for module, coverage in sorted(low_coverage, key=lambda x: x[1]):
                suggestions.append(f"  • {module} ({coverage:.1f}% coverage)")
        
        # Check for untested files
        untested_files = self.identify_untested_files()
        if untested_files:
            suggestions.append("\nCreate test files for these modules:")
            for file_path in untested_files[:5]:  # Show first 5
                suggestions.append(f"  • {file_path}")
            if len(untested_files) > 5:
                suggestions.append(f"  • ... and {len(untested_files) - 5} more")
        
        # General suggestions
        if any(coverage < 50 for coverage in module_coverage.values()):
            suggestions.append("\nGeneral suggestions:")
            suggestions.append("  • Add unit tests for public methods and functions")
            suggestions.append("  • Test error handling and edge cases")
            suggestions.append("  • Add integration tests for component interactions")
            suggestions.append("  • Use parametrized tests for multiple input scenarios")
        
        return suggestions


class TestMetrics:
    """Collects and analyzes test execution metrics."""
    
    def __init__(self):
        self.test_results = {}
        self.execution_times = {}
        self.failure_patterns = {}
    
    def record_test_result(self, test_name: str, passed: bool, execution_time: float) -> None:
        """Record the result of a test execution."""
        self.test_results[test_name] = passed
        self.execution_times[test_name] = execution_time
    
    def record_failure_pattern(self, test_name: str, failure_type: str, error_message: str) -> None:
        """Record patterns in test failures for analysis."""
        if failure_type not in self.failure_patterns:
            self.failure_patterns[failure_type] = []
        
        self.failure_patterns[failure_type].append({
            "test_name": test_name,
            "error_message": error_message
        })
    
    def get_test_summary(self) -> Dict[str, any]:
        """Get a summary of test execution metrics."""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for passed in self.test_results.values() if passed)
        failed_tests = total_tests - passed_tests
        
        avg_execution_time = (
            sum(self.execution_times.values()) / len(self.execution_times)
            if self.execution_times else 0
        )
        
        return {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "pass_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0,
            "avg_execution_time": avg_execution_time,
            "slowest_tests": self._get_slowest_tests(5),
            "failure_patterns": self.failure_patterns
        }
    
    def _get_slowest_tests(self, count: int) -> List[Tuple[str, float]]:
        """Get the slowest tests by execution time."""
        return sorted(
            self.execution_times.items(),
            key=lambda x: x[1],
            reverse=True
        )[:count]


def generate_test_template(module_path: str, class_name: str = None) -> str:
    """Generate a test file template for a given module."""
    module_name = Path(module_path).stem
    test_class_name = f"Test{class_name}" if class_name else f"Test{module_name.title()}"
    
    template = f'''"""
Unit tests for {module_path}.

This module contains comprehensive unit tests for the {module_name} module,
ensuring all functionality is properly tested and meets coverage requirements.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from tests.fixtures.test_fixtures import *
from tests.fixtures.mock_objects import *
from tests.utils.test_helpers import TestAssertions, AsyncTestHelper, MockHelper

from {module_path.replace("/", ".").replace(".py", "")} import *


class {test_class_name}:
    """Test suite for {module_name} functionality."""
    
    def test_initialization(self):
        """Test proper initialization of {module_name} components."""
        # TODO: Implement initialization tests
        pass
    
    @pytest.mark.asyncio
    async def test_async_operations(self):
        """Test async operations in {module_name}."""
        # TODO: Implement async operation tests
        pass
    
    def test_error_handling(self):
        """Test error handling in {module_name}."""
        # TODO: Implement error handling tests
        pass
    
    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # TODO: Implement edge case tests
        pass
    
    @pytest.mark.parametrize("input_value,expected", [
        # TODO: Add test parameters
    ])
    def test_parametrized_scenarios(self, input_value, expected):
        """Test multiple scenarios with different inputs."""
        # TODO: Implement parametrized tests
        pass


class {test_class_name}Integration:
    """Integration tests for {module_name} with other components."""
    
    @pytest.mark.asyncio
    async def test_component_integration(self, di_container):
        """Test integration with other POLARIS components."""
        # TODO: Implement integration tests
        pass
    
    def test_configuration_integration(self, test_config):
        """Test integration with configuration system."""
        # TODO: Implement configuration integration tests
        pass


# Performance tests
class {test_class_name}Performance:
    """Performance tests for {module_name}."""
    
    @pytest.mark.performance
    def test_performance_under_load(self):
        """Test performance characteristics under load."""
        # TODO: Implement performance tests
        pass
    
    @pytest.mark.performance
    async def test_concurrent_operations(self):
        """Test performance with concurrent operations."""
        # TODO: Implement concurrency tests
        pass
'''
    
    return template


def create_missing_test_files(source_dir: str = "src", test_dir: str = "tests") -> List[str]:
    """Create test file templates for modules that don't have tests."""
    created_files = []
    analyzer = CoverageAnalyzer(source_dir, test_dir)
    untested_files = analyzer.identify_untested_files()
    
    for file_path in untested_files:
        # Determine the appropriate test directory
        test_file_path = Path(test_dir) / "unit" / Path(file_path).parent / f"test_{Path(file_path).stem}.py"
        
        # Create directory if it doesn't exist
        test_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Generate and write test template
        template = generate_test_template(file_path)
        
        with open(test_file_path, 'w') as f:
            f.write(template)
        
        created_files.append(str(test_file_path))
    
    return created_files


if __name__ == "__main__":
    # Command-line interface for coverage analysis
    import argparse
    
    parser = argparse.ArgumentParser(description="POLARIS Coverage Analysis Tool")
    parser.add_argument("--analyze", action="store_true", help="Run coverage analysis")
    parser.add_argument("--create-templates", action="store_true", help="Create test templates for untested modules")
    parser.add_argument("--threshold", type=float, default=80.0, help="Coverage threshold percentage")
    
    args = parser.parse_args()
    
    analyzer = CoverageAnalyzer()
    analyzer.coverage_threshold = args.threshold
    
    if args.analyze:
        print("Running coverage analysis...")
        coverage_data = analyzer.run_coverage_analysis()
        report = analyzer.generate_coverage_report(coverage_data)
        print(report)
        
        suggestions = analyzer.suggest_test_improvements(coverage_data)
        if suggestions:
            print("\nSuggestions for improvement:")
            for suggestion in suggestions:
                print(suggestion)
    
    if args.create_templates:
        print("Creating test templates for untested modules...")
        created_files = create_missing_test_files()
        if created_files:
            print(f"Created {len(created_files)} test template files:")
            for file_path in created_files:
                print(f"  • {file_path}")
        else:
            print("No missing test files found.")