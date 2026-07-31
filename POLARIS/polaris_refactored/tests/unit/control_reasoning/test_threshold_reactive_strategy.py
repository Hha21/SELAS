"""
Unit tests for ThresholdReactiveStrategy Implementation

Comprehensive unit tests to verify the threshold-based reactive control strategy
works correctly with the existing framework.
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, patch
from typing import Dict, Any

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src'))

from control_reasoning.threshold_reactive_strategy import (
    ThresholdReactiveStrategy, ThresholdReactiveConfig, ThresholdRule,
    ThresholdCondition, ThresholdOperator, LogicalOperator
)
from control_reasoning.adaptive_controller import AdaptationNeed
from domain.models import AdaptationAction


class TestThresholdReactiveStrategy:
    """Test cases for ThresholdReactiveStrategy."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create test configuration with sample rules
        self.test_config = ThresholdReactiveConfig(
            rules=[
                ThresholdRule(
                    rule_id="cpu_high",
                    name="High CPU Usage",
                    conditions=[
                        ThresholdCondition(
                            metric_name="cpu_usage",
                            operator=ThresholdOperator.GREATER_THAN,
                            value=80.0,
                            weight=1.0
                        )
                    ],
                    action_type="scale_out",
                    action_parameters={"scale_factor": 2},
                    priority=3,
                    cooldown_seconds=30.0
                ),
                ThresholdRule(
                    rule_id="memory_critical",
                    name="Critical Memory Usage",
                    conditions=[
                        ThresholdCondition(
                            metric_name="memory_usage",
                            operator=ThresholdOperator.GREATER_EQUAL,
                            value=90.0,
                            weight=2.0
                        )
                    ],
                    action_type="emergency_scale",
                    action_parameters={"scale_factor": 3, "priority": "high"},
                    priority=5,
                    cooldown_seconds=60.0
                ),
                ThresholdRule(
                    rule_id="latency_range",
                    name="Latency in Acceptable Range",
                    conditions=[
                        ThresholdCondition(
                            metric_name="response_time",
                            operator=ThresholdOperator.BETWEEN,
                            value=[100.0, 500.0],
                            weight=1.0
                        )
                    ],
                    action_type="maintain_qos",
                    action_parameters={"qos_level": "normal"},
                    priority=1
                )
            ],
            max_concurrent_actions=2,
            enable_fallback=True
        )
        
        self.strategy = ThresholdReactiveStrategy(self.test_config)
    
    @pytest.mark.asyncio
    async def test_single_condition_trigger(self):
        """Test that a single condition triggers correctly."""
        system_id = "test_system"
        current_state = {
            "metrics": {
                "cpu_usage": 85.0,  # Above 80.0 threshold
                "memory_usage": 70.0,  # Below 90.0 threshold
                "response_time": 200.0  # Within 100-500 range
            }
        }
        adaptation_need = AdaptationNeed(system_id, True, "High resource usage")
        
        actions = await self.strategy.generate_actions(system_id, current_state, adaptation_need)
        
        # Should trigger cpu_high and latency_range rules
        assert len(actions) == 2  # Limited by max_concurrent_actions
        
        # Check that CPU rule triggered
        cpu_action = next((a for a in actions if a.action_type == "scale_out"), None)
        assert cpu_action is not None
        assert cpu_action.parameters["scale_factor"] == 2
        assert cpu_action.priority == 3
        
        # Check that latency rule triggered
        latency_action = next((a for a in actions if a.action_type == "maintain_qos"), None)
        assert latency_action is not None
        assert latency_action.parameters["qos_level"] == "normal"
    
    @pytest.mark.asyncio
    async def test_multiple_conditions_and_operator(self):
        """Test multiple conditions with AND operator."""
        # Create rule with multiple conditions
        multi_condition_rule = ThresholdRule(
            rule_id="multi_condition",
            name="Multiple Condition Rule",
            conditions=[
                ThresholdCondition("cpu_usage", ThresholdOperator.GREATER_THAN, 70.0),
                ThresholdCondition("memory_usage", ThresholdOperator.GREATER_THAN, 60.0)
            ],
            logical_operator=LogicalOperator.AND,
            action_type="optimize_resources",
            priority=2
        )
        
        config = ThresholdReactiveConfig(rules=[multi_condition_rule])
        strategy = ThresholdReactiveStrategy(config)
        
        # Test case where both conditions are met
        current_state = {
            "metrics": {
                "cpu_usage": 75.0,  # Above 70.0
                "memory_usage": 65.0  # Above 60.0
            }
        }
        adaptation_need = AdaptationNeed("test_system", True, "Resource optimization needed")
        
        actions = await strategy.generate_actions("test_system", current_state, adaptation_need)
        assert len(actions) == 1
        assert actions[0].action_type == "optimize_resources"
        
        # Test case where only one condition is met
        current_state["metrics"]["memory_usage"] = 50.0  # Below 60.0
        actions = await strategy.generate_actions("test_system", current_state, adaptation_need)
        assert len(actions) == 0  # AND operator requires both conditions
    
    @pytest.mark.asyncio
    async def test_or_operator(self):
        """Test multiple conditions with OR operator."""
        or_rule = ThresholdRule(
            rule_id="or_condition",
            name="OR Condition Rule",
            conditions=[
                ThresholdCondition("cpu_usage", ThresholdOperator.GREATER_THAN, 90.0),
                ThresholdCondition("memory_usage", ThresholdOperator.GREATER_THAN, 90.0)
            ],
            logical_operator=LogicalOperator.OR,
            action_type="emergency_action",
            priority=5
        )
        
        config = ThresholdReactiveConfig(rules=[or_rule])
        strategy = ThresholdReactiveStrategy(config)
        
        # Test case where only CPU condition is met
        current_state = {
            "metrics": {
                "cpu_usage": 95.0,  # Above 90.0
                "memory_usage": 70.0  # Below 90.0
            }
        }
        adaptation_need = AdaptationNeed("test_system", True, "Emergency situation")
        
        actions = await strategy.generate_actions("test_system", current_state, adaptation_need)
        assert len(actions) == 1
        assert actions[0].action_type == "emergency_action"
    
    @pytest.mark.asyncio
    async def test_between_operator(self):
        """Test BETWEEN operator for range conditions."""
        current_state = {
            "metrics": {
                "response_time": 300.0  # Within 100-500 range
            }
        }
        adaptation_need = AdaptationNeed("test_system", True, "Latency check")
        
        actions = await self.strategy.generate_actions("test_system", current_state, adaptation_need)
        
        # Should trigger latency_range rule
        latency_action = next((a for a in actions if a.action_type == "maintain_qos"), None)
        assert latency_action is not None
    
    @pytest.mark.asyncio
    async def test_outside_operator(self):
        """Test OUTSIDE operator for exclusion ranges."""
        outside_rule = ThresholdRule(
            rule_id="outside_range",
            name="Outside Range Rule",
            conditions=[
                ThresholdCondition(
                    metric_name="response_time",
                    operator=ThresholdOperator.OUTSIDE,
                    value=[100.0, 500.0]
                )
            ],
            action_type="fix_latency",
            priority=4
        )
        
        config = ThresholdReactiveConfig(rules=[outside_rule])
        strategy = ThresholdReactiveStrategy(config)
        
        # Test value outside range (too high)
        current_state = {
            "metrics": {
                "response_time": 600.0  # Above 500.0
            }
        }
        adaptation_need = AdaptationNeed("test_system", True, "Latency too high")
        
        actions = await strategy.generate_actions("test_system", current_state, adaptation_need)
        assert len(actions) == 1
        assert actions[0].action_type == "fix_latency"
        
        # Test value outside range (too low)
        current_state["metrics"]["response_time"] = 50.0  # Below 100.0
        actions = await strategy.generate_actions("test_system", current_state, adaptation_need)
        assert len(actions) == 1
        
        # Test value inside range
        current_state["metrics"]["response_time"] = 300.0  # Within 100-500
        actions = await strategy.generate_actions("test_system", current_state, adaptation_need)
        assert len(actions) == 0  # Should not trigger
    
    @pytest.mark.asyncio
    async def test_cooldown_period(self):
        """Test that cooldown periods prevent rapid rule re-triggering."""
        system_id = "test_system"
        current_state = {
            "metrics": {
                "cpu_usage": 85.0  # Above 80.0 threshold
            }
        }
        adaptation_need = AdaptationNeed(system_id, True, "High CPU")
        
        # First call should trigger
        actions1 = await self.strategy.generate_actions(system_id, current_state, adaptation_need)
        assert len(actions1) > 0
        
        # Immediate second call should not trigger due to cooldown
        actions2 = await self.strategy.generate_actions(system_id, current_state, adaptation_need)
        cpu_actions = [a for a in actions2 if a.action_type == "scale_out"]
        assert len(cpu_actions) == 0  # Should be in cooldown
    
    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """Test that actions are ordered by priority when prioritization is enabled."""
        system_id = "test_system"
        current_state = {
            "metrics": {
                "cpu_usage": 85.0,  # Triggers cpu_high (priority 3)
                "memory_usage": 95.0,  # Triggers memory_critical (priority 5)
                "response_time": 300.0  # Triggers latency_range (priority 1)
            }
        }
        adaptation_need = AdaptationNeed(system_id, True, "Multiple issues")
        
        actions = await self.strategy.generate_actions(system_id, current_state, adaptation_need)
        
        # Should be limited to max_concurrent_actions (2) and ordered by priority
        assert len(actions) == 2
        
        # First action should be highest priority (memory_critical, priority 5)
        assert actions[0].action_type == "emergency_scale"
        assert actions[0].priority == 5
        
        # Second action should be next highest (cpu_high, priority 3)
        assert actions[1].action_type == "scale_out"
        assert actions[1].priority == 3
    
    @pytest.mark.asyncio
    async def test_fallback_behavior(self):
        """Test fallback to simple reactive behavior when no rules trigger."""
        # Create strategy with no rules
        empty_config = ThresholdReactiveConfig(rules=[], enable_fallback=True)
        strategy = ThresholdReactiveStrategy(empty_config)
        
        system_id = "test_system"
        current_state = {
            "metrics": {
                "cpu": 0.9,  # High CPU for fallback logic
                "latency": 0.9  # High latency for fallback logic
            }
        }
        adaptation_need = AdaptationNeed(system_id, True, "Need adaptation")
        
        actions = await strategy.generate_actions(system_id, current_state, adaptation_need)
        
        # Should use fallback behavior from parent ReactiveControlStrategy
        assert len(actions) > 0
        # Check for typical fallback actions
        action_types = [a.action_type for a in actions]
        assert "scale_out" in action_types or "tune_qos" in action_types
    
    @pytest.mark.asyncio
    async def test_missing_metrics(self):
        """Test behavior when required metrics are missing."""
        system_id = "test_system"
        current_state = {
            "metrics": {
                "some_other_metric": 50.0
                # cpu_usage is missing
            }
        }
        adaptation_need = AdaptationNeed(system_id, True, "Missing metrics")
        
        actions = await self.strategy.generate_actions(system_id, current_state, adaptation_need)
        
        # Should not trigger rules that depend on missing metrics
        cpu_actions = [a for a in actions if a.action_type == "scale_out"]
        assert len(cpu_actions) == 0
    
    def test_configuration_validation(self):
        """Test configuration validation."""
        # Test invalid BETWEEN condition
        with pytest.raises(ValueError, match="BETWEEN/OUTSIDE operators require a list of exactly 2 values"):
            invalid_config = ThresholdReactiveConfig(
                rules=[
                    ThresholdRule(
                        rule_id="invalid_between",
                        name="Invalid Between Rule",
                        conditions=[
                            ThresholdCondition(
                                metric_name="test_metric",
                                operator=ThresholdOperator.BETWEEN,
                                value=100.0  # Should be a list of 2 values
                            )
                        ],
                        action_type="test_action"
                    )
                ]
            )
            ThresholdReactiveStrategy(invalid_config)
        
        # Test rule with no conditions
        with pytest.raises(ValueError, match="has no conditions defined"):
            invalid_config = ThresholdReactiveConfig(
                rules=[
                    ThresholdRule(
                        rule_id="no_conditions",
                        name="No Conditions Rule",
                        conditions=[],  # Empty conditions
                        action_type="test_action"
                    )
                ]
            )
            ThresholdReactiveStrategy(invalid_config)


if __name__ == "__main__":
    # Run a simple test
    async def run_simple_test():
        test_instance = TestThresholdReactiveStrategy()
        test_instance.setup_method()
        await test_instance.test_single_condition_trigger()
        print("✓ Basic threshold reactive strategy test passed!")
    
    asyncio.run(run_simple_test())