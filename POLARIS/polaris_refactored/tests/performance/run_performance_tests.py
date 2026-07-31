#!/usr/bin/env python3
"""
POLARIS Performance Test Runner

Dedicated runner for performance tests with specialized reporting and analysis.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
import json

from tests.performance.polaris_performance_test_suite import (
    PolarisPerformanceTestSuite, LoadTestConfig, PerformanceThresholds,
    run_basic_performance_suite, run_comprehensive_performance_suite
)


class PerformanceTestRunner:
    """Main runner for POLARIS performance tests."""
    
    def __init__(self, results_dir: str = "performance_results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(exist_ok=True)
        self.suite = PolarisPerformanceTestSuite(str(self.results_dir))
        
    async def run_quick_performance_check(self, systems: List[str]) -> bool:
        """Run quick performance validation."""
        print("🚀 Running Quick Performance Check...")
        
        try:
            results = await run_basic_performance_suite(systems)
            
            # Basic validation criteria
            throughput_ok = results["throughput"].throughput > 5.0
            latency_ok = results["latency"].avg_latency < 2.0
            error_rate_ok = results["throughput"].error_rate < 10.0
            
            all_ok = throughput_ok and latency_ok and error_rate_ok
            
            print(f"📊 Quick Performance Results:")
            print(f"  Throughput: {results['throughput'].throughput:.2f} ops/sec {'✅' if throughput_ok else '❌'}")
            print(f"  Latency: {results['latency'].avg_latency*1000:.2f} ms {'✅' if latency_ok else '❌'}")
            print(f"  Error Rate: {results['throughput'].error_rate:.2f}% {'✅' if error_rate_ok else '❌'}")
            print(f"  Overall: {'✅ PASS' if all_ok else '❌ FAIL'}")
            
            return all_ok
            
        except Exception as e:
            print(f"❌ Quick performance check failed: {e}")
            return False
    
    async def run_throughput_benchmark(
        self, 
        systems: List[str], 
        duration: float = 60.0,
        concurrent_users: int = 20,
        target_throughput: Optional[float] = None
    ) -> bool:
        """Run throughput benchmark."""
        print(f"📈 Running Throughput Benchmark ({duration}s, {concurrent_users} users)...")
        
        config = LoadTestConfig(
            test_name="throughput_benchmark",
            duration=duration,
            concurrent_users=concurrent_users,
            ramp_up_time=min(duration * 0.2, 15.0),
            target_throughput=target_throughput,
            warmup_duration=5.0
        )
        
        thresholds = PerformanceThresholds(
            min_throughput=target_throughput * 0.8 if target_throughput else 10.0,
            max_avg_latency=1.0,
            max_p95_latency=2.0,
            max_error_rate=5.0,
            max_cpu_usage=85.0
        )
        
        try:
            metrics, passed = await self.suite.run_throughput_test(systems, config, thresholds)
            
            print(f"📊 Throughput Benchmark Results:")
            print(f"  Throughput: {metrics.throughput:.2f} ops/sec")
            print(f"  Average Latency: {metrics.avg_latency*1000:.2f} ms")
            print(f"  P95 Latency: {metrics.p95_latency*1000:.2f} ms")
            print(f"  P99 Latency: {metrics.p99_latency*1000:.2f} ms")
            print(f"  Error Rate: {metrics.error_rate:.2f}%")
            print(f"  CPU Usage: {metrics.cpu_usage.get('cpu_avg', 0):.1f}%")
            print(f"  Result: {'✅ PASS' if passed else '❌ FAIL'}")
            
            return passed
            
        except Exception as e:
            print(f"❌ Throughput benchmark failed: {e}")
            return False
    
    async def run_latency_benchmark(
        self,
        systems: List[str],
        duration: float = 30.0,
        concurrent_users: int = 5
    ) -> bool:
        """Run latency benchmark."""
        print(f"⚡ Running Latency Benchmark ({duration}s, {concurrent_users} users)...")
        
        config = LoadTestConfig(
            test_name="latency_benchmark",
            duration=duration,
            concurrent_users=concurrent_users,
            ramp_up_time=5.0,
            warmup_duration=3.0
        )
        
        thresholds = PerformanceThresholds(
            max_avg_latency=0.5,
            max_p95_latency=1.0,
            max_p99_latency=2.0,
            max_error_rate=2.0
        )
        
        try:
            metrics, passed = await self.suite.run_latency_test(systems, config, thresholds)
            
            print(f"📊 Latency Benchmark Results:")
            print(f"  Average Latency: {metrics.avg_latency*1000:.2f} ms")
            print(f"  P50 Latency: {metrics.p50_latency*1000:.2f} ms")
            print(f"  P95 Latency: {metrics.p95_latency*1000:.2f} ms")
            print(f"  P99 Latency: {metrics.p99_latency*1000:.2f} ms")
            print(f"  Max Latency: {metrics.max_latency*1000:.2f} ms")
            print(f"  Min Latency: {metrics.min_latency*1000:.2f} ms")
            print(f"  Error Rate: {metrics.error_rate:.2f}%")
            print(f"  Result: {'✅ PASS' if passed else '❌ FAIL'}")
            
            return passed
            
        except Exception as e:
            print(f"❌ Latency benchmark failed: {e}")
            return False
    
    async def run_stress_test(
        self,
        systems: List[str],
        duration: float = 120.0,
        concurrent_users: int = 30
    ) -> bool:
        """Run stress test."""
        print(f"💪 Running Stress Test ({duration}s, {concurrent_users} users)...")
        
        config = LoadTestConfig(
            test_name="stress_test",
            duration=duration,
            concurrent_users=concurrent_users,
            ramp_up_time=20.0,
            ramp_down_time=10.0,
            max_errors=100,
            warmup_duration=10.0
        )
        
        # More lenient thresholds for stress test
        thresholds = PerformanceThresholds(
            min_throughput=5.0,
            max_avg_latency=3.0,
            max_error_rate=15.0,
            max_cpu_usage=95.0
        )
        
        try:
            metrics, passed = await self.suite.run_stress_test(systems, config, thresholds)
            
            print(f"📊 Stress Test Results:")
            print(f"  Duration: {metrics.duration:.1f}s")
            print(f"  Throughput: {metrics.throughput:.2f} ops/sec")
            print(f"  Average Latency: {metrics.avg_latency*1000:.2f} ms")
            print(f"  P95 Latency: {metrics.p95_latency*1000:.2f} ms")
            print(f"  Error Rate: {metrics.error_rate:.2f}%")
            print(f"  CPU Usage: {metrics.cpu_usage.get('cpu_avg', 0):.1f}%")
            print(f"  Memory Usage: {metrics.memory_usage.get('memory_avg', 0):.1f} MB")
            print(f"  Result: {'✅ PASS' if passed else '❌ FAIL'}")
            
            return passed
            
        except Exception as e:
            print(f"❌ Stress test failed: {e}")
            return False
    
    async def run_scalability_test(
        self,
        base_systems: List[str],
        max_scale_factor: int = 4,
        duration: float = 30.0
    ) -> bool:
        """Run scalability test."""
        print(f"📈 Running Scalability Test (up to {max_scale_factor}x scale)...")
        
        scale_factors = [2**i for i in range(max_scale_factor.bit_length())]  # Powers of 2 up to max
        scale_factors = [f for f in scale_factors if f <= max_scale_factor]
        
        base_config = LoadTestConfig(
            test_name="scalability_test",
            duration=duration,
            concurrent_users=5,
            ramp_up_time=5.0
        )
        
        thresholds = PerformanceThresholds(
            min_throughput=2.0,
            max_avg_latency=2.0,
            max_error_rate=10.0
        )
        
        try:
            results = await self.suite.run_scalability_test(
                base_systems, scale_factors, base_config, thresholds
            )
            
            print(f"📊 Scalability Test Results:")
            
            throughputs = []
            all_passed = True
            
            for scale_factor, metrics, passed in results:
                throughputs.append(metrics.throughput)
                status = "✅ PASS" if passed else "❌ FAIL"
                print(f"  {scale_factor}x: {metrics.throughput:.2f} ops/sec, {metrics.avg_latency*1000:.2f} ms, {metrics.error_rate:.2f}% errors {status}")
                all_passed = all_passed and passed
            
            # Calculate scaling efficiency
            if len(throughputs) > 1:
                scaling_efficiency = (throughputs[-1] / throughputs[0]) / scale_factors[-1]
                print(f"  Scaling Efficiency: {scaling_efficiency:.2f} ({scaling_efficiency*100:.1f}%)")
            
            print(f"  Overall: {'✅ PASS' if all_passed else '❌ FAIL'}")
            
            return all_passed
            
        except Exception as e:
            print(f"❌ Scalability test failed: {e}")
            return False
    
    async def run_endurance_test(
        self,
        systems: List[str],
        duration_hours: float = 1.0,
        concurrent_users: int = 10
    ) -> bool:
        """Run endurance test."""
        print(f"🏃 Running Endurance Test ({duration_hours}h, {concurrent_users} users)...")
        
        try:
            metrics, passed = await self.suite.run_endurance_test(
                systems, duration_hours, 
                LoadTestConfig(
                    test_name="endurance_test",
                    concurrent_users=concurrent_users,
                    ramp_up_time=30.0
                ),
                PerformanceThresholds(
                    min_throughput=5.0,
                    max_avg_latency=2.0,
                    max_error_rate=10.0
                )
            )
            
            print(f"📊 Endurance Test Results:")
            print(f"  Duration: {metrics.duration/3600:.2f} hours")
            print(f"  Throughput: {metrics.throughput:.2f} ops/sec")
            print(f"  Average Latency: {metrics.avg_latency*1000:.2f} ms")
            print(f"  Error Rate: {metrics.error_rate:.2f}%")
            print(f"  Result: {'✅ PASS' if passed else '❌ FAIL'}")
            
            return passed
            
        except Exception as e:
            print(f"❌ Endurance test failed: {e}")
            return False
    
    async def run_comprehensive_suite(self, systems: List[str]) -> Dict[str, bool]:
        """Run comprehensive performance test suite."""
        print("🎯 Running Comprehensive Performance Suite...")
        
        try:
            results = await run_comprehensive_performance_suite(systems)
            
            # Extract pass/fail status
            test_results = {
                "throughput": results["throughput"]["passed"],
                "stress": results["stress"]["passed"],
                "scalability": all(passed for _, _, passed in results["scalability"])
            }
            
            # Print summary
            print(f"\n📋 Comprehensive Suite Summary:")
            for test_name, passed in test_results.items():
                status = "✅ PASS" if passed else "❌ FAIL"
                print(f"  {test_name.title()}: {status}")
            
            overall_pass = all(test_results.values())
            print(f"  Overall: {'✅ PASS' if overall_pass else '❌ FAIL'}")
            
            # Save detailed report
            report_file = self.results_dir / f"comprehensive_report_{int(time.time())}.txt"
            with open(report_file, 'w') as f:
                f.write(results["report"])
            
            print(f"\n📄 Detailed report saved to: {report_file}")
            
            return test_results
            
        except Exception as e:
            print(f"❌ Comprehensive suite failed: {e}")
            return {}
    
    def generate_summary_report(self) -> str:
        """Generate summary report of all performance tests."""
        if not self.suite.test_results:
            return "No performance test results available."
        
        return self.suite.generate_performance_report(include_charts=True)


def main():
    """Main entry point for performance test runner."""
    parser = argparse.ArgumentParser(
        description="POLARIS Performance Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m tests.performance.run_performance_tests --quick
  python -m tests.performance.run_performance_tests --throughput --duration 60 --users 20
  python -m tests.performance.run_performance_tests --latency --duration 30 --users 5
  python -m tests.performance.run_performance_tests --stress --duration 120 --users 30
  python -m tests.performance.run_performance_tests --scalability --max-scale 8
  python -m tests.performance.run_performance_tests --endurance --hours 2
  python -m tests.performance.run_performance_tests --comprehensive
        """
    )
    
    # Test type options
    parser.add_argument("--quick", action="store_true", help="Run quick performance check")
    parser.add_argument("--throughput", action="store_true", help="Run throughput benchmark")
    parser.add_argument("--latency", action="store_true", help="Run latency benchmark")
    parser.add_argument("--stress", action="store_true", help="Run stress test")
    parser.add_argument("--scalability", action="store_true", help="Run scalability test")
    parser.add_argument("--endurance", action="store_true", help="Run endurance test")
    parser.add_argument("--comprehensive", action="store_true", help="Run comprehensive test suite")
    
    # Configuration options
    parser.add_argument("--systems", nargs="+", default=["perf_system_1", "perf_system_2"], help="Systems to test")
    parser.add_argument("--duration", type=float, default=60.0, help="Test duration in seconds")
    parser.add_argument("--users", type=int, default=10, help="Concurrent users")
    parser.add_argument("--target-throughput", type=float, help="Target throughput (ops/sec)")
    parser.add_argument("--max-scale", type=int, default=4, help="Maximum scale factor for scalability test")
    parser.add_argument("--hours", type=float, default=1.0, help="Duration in hours for endurance test")
    parser.add_argument("--results-dir", default="performance_results", help="Results directory")
    
    args = parser.parse_args()
    
    # Initialize runner
    runner = PerformanceTestRunner(args.results_dir)
    
    async def run_tests():
        """Run the selected performance tests."""
        results = {}
        
        try:
            if args.quick:
                results["quick"] = await runner.run_quick_performance_check(args.systems)
            
            if args.throughput:
                results["throughput"] = await runner.run_throughput_benchmark(
                    args.systems, args.duration, args.users, args.target_throughput
                )
            
            if args.latency:
                results["latency"] = await runner.run_latency_benchmark(
                    args.systems, args.duration, args.users
                )
            
            if args.stress:
                results["stress"] = await runner.run_stress_test(
                    args.systems, args.duration, args.users
                )
            
            if args.scalability:
                results["scalability"] = await runner.run_scalability_test(
                    args.systems[:2], args.max_scale, args.duration
                )
            
            if args.endurance:
                results["endurance"] = await runner.run_endurance_test(
                    args.systems, args.hours, args.users
                )
            
            if args.comprehensive:
                comprehensive_results = await runner.run_comprehensive_suite(args.systems)
                results.update(comprehensive_results)
            
            # If no specific test selected, run quick check
            if not any([args.quick, args.throughput, args.latency, args.stress, 
                       args.scalability, args.endurance, args.comprehensive]):
                results["quick"] = await runner.run_quick_performance_check(args.systems)
            
            # Generate summary
            if results:
                print(f"\n{'='*60}")
                print("PERFORMANCE TEST SUMMARY")
                print(f"{'='*60}")
                
                passed_tests = sum(1 for passed in results.values() if passed)
                total_tests = len(results)
                
                for test_name, passed in results.items():
                    status = "✅ PASS" if passed else "❌ FAIL"
                    print(f"{test_name.upper()}: {status}")
                
                overall_status = "✅ ALL PASSED" if passed_tests == total_tests else f"❌ {total_tests - passed_tests}/{total_tests} FAILED"
                print(f"\nOVERALL: {overall_status}")
                print(f"{'='*60}")
                
                # Generate detailed report
                summary_report = runner.generate_summary_report()
                report_file = Path(args.results_dir) / f"summary_report_{int(time.time())}.txt"
                with open(report_file, 'w') as f:
                    f.write(summary_report)
                
                print(f"\n📄 Summary report saved to: {report_file}")
                
                return passed_tests == total_tests
            else:
                print("❌ No tests were run")
                return False
                
        except KeyboardInterrupt:
            print("\n👋 Performance tests interrupted")
            return False
        except Exception as e:
            print(f"❌ Performance test execution failed: {e}")
            return False
    
    # Run tests
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()