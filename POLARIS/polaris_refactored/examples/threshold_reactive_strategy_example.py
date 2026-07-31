"""
Threshold Reactive Strategy Example

Demonstrates how to use the ThresholdReactiveStrategy with the POLARIS framework.
This example shows configuration, rule setup, and execution of threshold-based
reactive control strategies.
"""

import asyncio
import logging
import sys
import os
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

from control_reasoning.threshold_reactive_strategy import (
    ThresholdReactiveStrategy, ThresholdReactiveConfig, ThresholdRule,
    ThresholdCondition, ThresholdOperator, LogicalOperator
)
from control_reasoning.adaptive_controller import AdaptationNeed
from domain.models import AdaptationAction


async def main():
    """Main example demonstrating threshold reactive strategy usage."""
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    logger.info("Starting Threshold Reactive Strategy Example")
    
    # Create comprehensive threshold configuration
    config = create_comprehensive_config()
    
    # Initialize the strategy
    strategy = ThresholdReactiveStrategy(config)
    
    # Test scenarios
    scenarios = [
        create_high_cpu_scenario(),
        create_memory_pressure_scenario(),
        create_latency_spike_scenario(),
        create_multi_metric_crisis_scenario(),
        create_normal_operations_scenario()
    ]
    
    # Execute each scenario
    for i, scenario in enumerate(scenarios, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"SCENARIO {i}: {scenario['name']}")
        logger.info(f"Description: {scenario['description']}")
        logger.info(f"{'='*60}")
        
        try:
            # Execute the strategy
            actions = await strategy.generate_actions(
                scenario['system_id'],
                scenario['current_state'],
                scenario['adaptation_need']
            )
            
            # Display results
            display_scenario_results(scenario, actions, logger)
            
        except Exception as e:
            logger.error(f"Scenario {i} failed with error: {str(e)}")
    
    logger.info("\nThreshold Reactive Strategy Example completed")


def create_comprehensive_config() -> ThresholdReactiveConfig:
    """Create a comprehensive threshold configuration with various rule types."""
    
    rules = [
        # High CPU usage rule
        ThresholdRule(
            rule_id="cpu_high",
            name="High CPU Usage",
            conditions=[
                ThresholdCondition(
                    metric_name="cpu_usage",
                    operator=ThresholdOperator.GREATER_THAN,
                    value=80.0,
                    weight=2.0,
                    description="CPU usage above 80%"
                )
            ],
            action_type="scale_out",
            action_parameters={
                "scale_factor": 2,
                "resource_type": "cpu",
                "urgency": "high"
            },
            priority=4,
            cooldown_seconds=60.0,
            description="Scale out when CPU usage is high"
        ),
        
        # Critical memory usage rule
        ThresholdRule(
            rule_id="memory_critical",
            name="Critical Memory Usage",
            conditions=[
                ThresholdCondition(
                    metric_name="memory_usage",
                    operator=ThresholdOperator.GREATER_EQUAL,
                    value=90.0,
                    weight=3.0,
                    description="Memory usage at or above 90%"
                )
            ],
            action_type="emergency_scale",
            action_parameters={
                "scale_factor": 3,
                "resource_type": "memory",
                "urgency": "critical"
            },
            priority=5,
            cooldown_seconds=30.0,
            description="Emergency scaling for critical memory usage"
        ),
        
        # Latency in acceptable range rule
        ThresholdRule(
            rule_id="latency_normal",
            name="Latency in Normal Range",
            conditions=[
                ThresholdCondition(
                    metric_name="response_time",
                    operator=ThresholdOperator.BETWEEN,
                    value=[50.0, 200.0],
                    weight=1.0,
                    description="Response time between 50-200ms"
                )
            ],
            action_type="maintain_qos",
            action_parameters={
                "qos_level": "normal",
                "optimization": "balanced"
            },
            priority=1,
            cooldown_seconds=120.0,
            description="Maintain QoS when latency is in normal range"
        ),
        
        # High latency rule
        ThresholdRule(
            rule_id="latency_high",
            name="High Latency",
            conditions=[
                ThresholdCondition(
                    metric_name="response_time",
                    operator=ThresholdOperator.GREATER_THAN,
                    value=500.0,
                    weight=2.5,
                    description="Response time above 500ms"
                )
            ],
            action_type="optimize_performance",
            action_parameters={
                "optimization_type": "latency",
                "cache_boost": True,
                "connection_pool_size": 50
            },
            priority=4,
            cooldown_seconds=45.0,
            description="Optimize performance when latency is high"
        ),
        
        # Multi-condition resource pressure rule
        ThresholdRule(
            rule_id="resource_pressure",
            name="Resource Pressure",
            conditions=[
                ThresholdCondition(
                    metric_name="cpu_usage",
                    operator=ThresholdOperator.GREATER_THAN,
                    value=70.0,
                    weight=1.5
                ),
                ThresholdCondition(
                    metric_name="memory_usage",
                    operator=ThresholdOperator.GREATER_THAN,
                    value=75.0,
                    weight=1.5
                )
            ],
            logical_operator=LogicalOperator.AND,
            action_type="resource_optimization",
            action_parameters={
                "optimization_strategy": "comprehensive",
                "gc_tuning": True,
                "connection_cleanup": True
            },
            priority=3,
            cooldown_seconds=90.0,
            description="Optimize resources when both CPU and memory are under pressure"
        ),
        
        # Error rate spike rule
        ThresholdRule(
            rule_id="error_spike",
            name="Error Rate Spike",
            conditions=[
                ThresholdCondition(
                    metric_name="error_rate",
                    operator=ThresholdOperator.GREATER_THAN,
                    value=5.0,
                    weight=3.0,
                    description="Error rate above 5%"
                )
            ],
            action_type="circuit_breaker",
            action_parameters={
                "action": "enable",
                "timeout": 30,
                "fallback_service": "backup_service"
            },
            priority=5,
            cooldown_seconds=20.0,
            description="Enable circuit breaker on high error rates"
        )
    ]
    
    return ThresholdReactiveConfig(
        rules=rules,
        enable_multi_metric_evaluation=True,
        action_prioritization_enabled=True,
        max_concurrent_actions=3,
        default_cooldown_seconds=60.0,
        severity_weights={
            "critical": 3.0,
            "high": 2.0,
            "medium": 1.0,
            "low": 0.5
        },
        enable_fallback=True
    )


def create_high_cpu_scenario() -> Dict[str, Any]:
    """Create a high CPU usage scenario."""
    return {
        "name": "High CPU Usage",
        "description": "System experiencing high CPU utilization",
        "system_id": "web_service_001",
        "current_state": {
            "metrics": {
                "cpu_usage": 85.0,  # Above 80% threshold
                "memory_usage": 65.0,
                "response_time": 150.0,
                "error_rate": 1.2
            }
        },
        "adaptation_need": AdaptationNeed("web_service_001", True, "High CPU usage detected")
    }


def create_memory_pressure_scenario() -> Dict[str, Any]:
    """Create a memory pressure scenario."""
    return {
        "name": "Memory Pressure",
        "description": "System experiencing critical memory usage",
        "system_id": "api_service_002",
        "current_state": {
            "metrics": {
                "cpu_usage": 60.0,
                "memory_usage": 92.0,  # Above 90% threshold
                "response_time": 200.0,
                "error_rate": 2.1
            }
        },
        "adaptation_need": AdaptationNeed("api_service_002", True, "Critical memory usage")
    }


def create_latency_spike_scenario() -> Dict[str, Any]:
    """Create a latency spike scenario."""
    return {
        "name": "Latency Spike",
        "description": "System experiencing high response times",
        "system_id": "payment_service_003",
        "current_state": {
            "metrics": {
                "cpu_usage": 45.0,
                "memory_usage": 55.0,
                "response_time": 750.0,  # Above 500ms threshold
                "error_rate": 3.5
            }
        },
        "adaptation_need": AdaptationNeed("payment_service_003", True, "High latency detected")
    }


def create_multi_metric_crisis_scenario() -> Dict[str, Any]:
    """Create a scenario with multiple metrics exceeding thresholds."""
    return {
        "name": "Multi-Metric Crisis",
        "description": "System experiencing multiple issues simultaneously",
        "system_id": "critical_service_004",
        "current_state": {
            "metrics": {
                "cpu_usage": 88.0,  # High CPU
                "memory_usage": 94.0,  # Critical memory
                "response_time": 850.0,  # High latency
                "error_rate": 7.2  # High error rate
            }
        },
        "adaptation_need": AdaptationNeed("critical_service_004", True, "Multiple critical issues")
    }


def create_normal_operations_scenario() -> Dict[str, Any]:
    """Create a normal operations scenario."""
    return {
        "name": "Normal Operations",
        "description": "System operating within normal parameters",
        "system_id": "stable_service_005",
        "current_state": {
            "metrics": {
                "cpu_usage": 45.0,
                "memory_usage": 60.0,
                "response_time": 120.0,  # Within 50-200ms range
                "error_rate": 0.5
            }
        },
        "adaptation_need": AdaptationNeed("stable_service_005", False, "System stable")
    }


def display_scenario_results(scenario: Dict[str, Any], actions: list, logger):
    """Display the results of a scenario execution."""
    
    logger.info(f"System ID: {scenario['system_id']}")
    logger.info(f"Metrics: {scenario['current_state']['metrics']}")
    logger.info(f"Adaptation Needed: {scenario['adaptation_need'].is_needed}")
    
    if actions:
        logger.info(f"\nGenerated {len(actions)} actions:")
        for i, action in enumerate(actions, 1):
            logger.info(f"  {i}. Action Type: {action.action_type}")
            logger.info(f"     Priority: {action.priority}")
            logger.info(f"     Parameters: {action.parameters}")
            logger.info(f"     Description: {action.description}")
            if i < len(actions):
                logger.info("")
    else:
        logger.info("\nNo actions generated")
        if scenario['adaptation_need'].is_needed:
            logger.info("(Fallback behavior may have been used)")


if __name__ == "__main__":
    asyncio.run(main())