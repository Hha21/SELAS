"""
Threshold-Based Reactive Control Strategy Implementation

Implements a configurable threshold-based reactive control strategy that extends
the existing ReactiveControlStrategy class. This strategy provides rule-based
adaptation responses based on configurable metric thresholds with multi-metric
evaluation and action prioritization.

Key Features:
- Configurable threshold rules for multiple metrics
- Multi-metric threshold evaluation with logical operators
- Action prioritization based on severity and impact
- Support for complex threshold conditions (ranges, combinations)
- Integration with existing observability framework
- Fallback to simple reactive behavior when configuration fails
"""

import time
import uuid
from typing import List, Dict, Any, Optional, Union, Callable
from dataclasses import dataclass, field
from enum import Enum

from .adaptive_controller import ReactiveControlStrategy, AdaptationNeed
from ..domain.models import AdaptationAction, MetricValue
from ..infrastructure.observability import (
    get_logger, get_metrics_collector, get_tracer, observe_polaris_component,
    trace_adaptation_flow
)


class ThresholdOperator(Enum):
    """Operators for threshold comparisons."""
    GREATER_THAN = "gt"
    GREATER_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_EQUAL = "lte"
    EQUAL = "eq"
    NOT_EQUAL = "neq"
    BETWEEN = "between"
    OUTSIDE = "outside"


class LogicalOperator(Enum):
    """Logical operators for combining multiple conditions."""
    AND = "and"
    OR = "or"
    NOT = "not"


@dataclass
class ThresholdCondition:
    """Represents a single threshold condition."""
    metric_name: str
    operator: ThresholdOperator
    value: Union[float, List[float]]  # Single value or range for BETWEEN/OUTSIDE
    weight: float = 1.0  # Weight for prioritization
    description: Optional[str] = None


@dataclass
class ThresholdRule:
    """Represents a complete threshold rule with conditions and actions."""
    rule_id: str
    name: str
    conditions: List[ThresholdCondition]
    logical_operator: LogicalOperator = LogicalOperator.AND
    action_type: str = ""
    action_parameters: Dict[str, Any] = field(default_factory=dict)
    priority: int = 1  # Higher number = higher priority
    cooldown_seconds: float = 60.0  # Minimum time between rule activations
    enabled: bool = True
    description: Optional[str] = None


@dataclass
class ThresholdReactiveConfig:
    """Configuration for Threshold Reactive Strategy."""
    rules: List[ThresholdRule] = field(default_factory=list)
    enable_multi_metric_evaluation: bool = True
    action_prioritization_enabled: bool = True
    max_concurrent_actions: int = 5
    default_cooldown_seconds: float = 60.0
    severity_weights: Dict[str, float] = field(default_factory=lambda: {
        "critical": 3.0,
        "high": 2.0,
        "medium": 1.0,
        "low": 0.5
    })
    enable_fallback: bool = True


@dataclass
class RuleEvaluationResult:
    """Result of evaluating a threshold rule."""
    rule_id: str
    triggered: bool
    severity_score: float
    conditions_met: List[str]
    conditions_failed: List[str]
    evaluation_time: float
    error_message: Optional[str] = None


@observe_polaris_component("threshold_reactive_strategy", auto_trace=True, auto_metrics=True)
class ThresholdReactiveStrategy(ReactiveControlStrategy):
    """
    Threshold-based Reactive Control Strategy.
    
    Extends ReactiveControlStrategy to provide configurable rule-based adaptation
    responses based on metric thresholds. Supports complex threshold conditions,
    multi-metric evaluation, and action prioritization.
    
    Key Features:
    - Configurable threshold rules with multiple conditions
    - Support for complex operators (between, outside ranges)
    - Multi-metric evaluation with logical operators (AND, OR, NOT)
    - Action prioritization based on severity and impact
    - Cooldown periods to prevent action flooding
    - Integration with existing observability framework
    - Fallback to simple reactive behavior when rules fail
    """
    
    def __init__(self, config: Optional[ThresholdReactiveConfig] = None):
        """Initialize the Threshold Reactive Strategy."""
        self.config = config or ThresholdReactiveConfig()
        self.logger = get_logger(self.__class__.__name__)
        self.metrics_collector = get_metrics_collector()
        self.tracer = get_tracer()
        
        # Track rule activation times for cooldown management
        self._rule_last_triggered: Dict[str, float] = {}
        
        # Validate configuration
        self._validate_config()
        
        self.logger.info(
            f"Initialized ThresholdReactiveStrategy with {len(self.config.rules)} rules",
            extra={
                "rules_count": len(self.config.rules),
                "multi_metric_enabled": self.config.enable_multi_metric_evaluation,
                "prioritization_enabled": self.config.action_prioritization_enabled
            }
        )
    
    def _validate_config(self) -> None:
        """Validate the threshold configuration."""
        if not self.config.rules:
            self.logger.warning("No threshold rules configured, strategy will use fallback behavior")
            return
        
        for rule in self.config.rules:
            if not rule.conditions:
                raise ValueError(f"Rule {rule.rule_id} has no conditions defined")
            
            for condition in rule.conditions:
                if condition.operator in [ThresholdOperator.BETWEEN, ThresholdOperator.OUTSIDE]:
                    if not isinstance(condition.value, list) or len(condition.value) != 2:
                        raise ValueError(
                            f"Rule {rule.rule_id}, condition {condition.metric_name}: "
                            f"BETWEEN/OUTSIDE operators require a list of exactly 2 values"
                        )
    
    @trace_adaptation_flow("threshold_strategy_generate_actions")
    async def generate_actions(
        self, 
        system_id: str, 
        current_state: Dict[str, Any],
        adaptation_need: AdaptationNeed
    ) -> List[AdaptationAction]:
        """
        Generate adaptation actions based on threshold rules.
        
        Args:
            system_id: ID of the system being adapted
            current_state: Current system state including metrics
            adaptation_need: Identified adaptation need
            
        Returns:
            List of adaptation actions to execute
        """
        start_time = time.time()
        actions: List[AdaptationAction] = []
        
        try:
            metrics = current_state.get("metrics", {})
            
            # Evaluate all threshold rules
            rule_results = await self._evaluate_rules(metrics, system_id)
            
            # Generate actions from triggered rules
            triggered_rules = [result for result in rule_results if result.triggered]
            
            if triggered_rules:
                actions = await self._generate_actions_from_rules(
                    triggered_rules, system_id, metrics
                )
                
                self.logger.info(
                    f"Generated {len(actions)} actions from {len(triggered_rules)} triggered rules",
                    extra={
                        "system_id": system_id,
                        "triggered_rules": [r.rule_id for r in triggered_rules],
                        "actions_count": len(actions)
                    }
                )
            else:
                self.logger.debug(
                    f"No threshold rules triggered for system {system_id}",
                    extra={"system_id": system_id, "rules_evaluated": len(rule_results)}
                )
            
            # Fallback to simple reactive behavior if no rules triggered and fallback enabled
            # Only fallback if no threshold rules were configured or all failed to evaluate
            should_fallback = (
                self.config.enable_fallback and 
                adaptation_need.is_needed and 
                not actions and 
                (not self.config.rules or all(not r.enabled for r in self.config.rules))
            )
            
            if should_fallback:
                actions = await self._fallback_generate_actions(system_id, current_state, adaptation_need)
                self.logger.info(
                    f"Used fallback strategy, generated {len(actions)} actions",
                    extra={"system_id": system_id, "fallback_actions": len(actions)}
                )
            
            # Record metrics
            execution_time = time.time() - start_time
            self.metrics_collector.record_histogram(
                "threshold_strategy_execution_time",
                execution_time,
                tags={"system_id": system_id}
            )
            self.metrics_collector.record_counter(
                "threshold_strategy_actions_generated",
                len(actions),
                tags={"system_id": system_id}
            )
            
            return actions
            
        except Exception as e:
            self.logger.error(
                f"Error generating threshold-based actions: {e}",
                extra={"system_id": system_id, "error": str(e)},
                exc_info=True
            )
            
            # Fallback on error if enabled
            if self.config.enable_fallback:
                return await self._fallback_generate_actions(system_id, current_state, adaptation_need)
            
            return []
    
    async def _evaluate_rules(
        self, 
        metrics: Dict[str, Any], 
        system_id: str
    ) -> List[RuleEvaluationResult]:
        """Evaluate all threshold rules against current metrics."""
        results: List[RuleEvaluationResult] = []
        current_time = time.time()
        
        for rule in self.config.rules:
            if not rule.enabled:
                continue
            
            try:
                result = await self._evaluate_single_rule(rule, metrics)
                
                # Check cooldown period only if rule would trigger
                if result.triggered:
                    last_triggered = self._rule_last_triggered.get(rule.rule_id, 0)
                    if current_time - last_triggered < rule.cooldown_seconds:
                        self.logger.debug(
                            f"Rule {rule.rule_id} in cooldown period",
                            extra={
                                "rule_id": rule.rule_id,
                                "cooldown_remaining": rule.cooldown_seconds - (current_time - last_triggered)
                            }
                        )
                        # Create a non-triggered result for cooldown
                        result = RuleEvaluationResult(
                            rule_id=rule.rule_id,
                            triggered=False,
                            severity_score=0.0,
                            conditions_met=[],
                            conditions_failed=["cooldown_active"],
                            evaluation_time=result.evaluation_time,
                            error_message="Rule in cooldown period"
                        )
                    else:
                        # Update last triggered time
                        self._rule_last_triggered[rule.rule_id] = current_time
                
                results.append(result)
                    
            except Exception as e:
                self.logger.error(
                    f"Error evaluating rule {rule.rule_id}: {e}",
                    extra={"rule_id": rule.rule_id, "error": str(e)},
                    exc_info=True
                )
                results.append(RuleEvaluationResult(
                    rule_id=rule.rule_id,
                    triggered=False,
                    severity_score=0.0,
                    conditions_met=[],
                    conditions_failed=[],
                    evaluation_time=0.0,
                    error_message=str(e)
                ))
        
        return results
    
    async def _evaluate_single_rule(
        self, 
        rule: ThresholdRule, 
        metrics: Dict[str, Any]
    ) -> RuleEvaluationResult:
        """Evaluate a single threshold rule."""
        start_time = time.time()
        conditions_met: List[str] = []
        conditions_failed: List[str] = []
        condition_results: List[bool] = []
        
        # Evaluate each condition
        for condition in rule.conditions:
            try:
                result = self._evaluate_condition(condition, metrics)
                condition_results.append(result)
                
                if result:
                    conditions_met.append(condition.metric_name)
                else:
                    conditions_failed.append(condition.metric_name)
                    
            except Exception as e:
                self.logger.warning(
                    f"Failed to evaluate condition for metric {condition.metric_name}: {e}",
                    extra={"rule_id": rule.rule_id, "metric": condition.metric_name, "error": str(e)}
                )
                condition_results.append(False)
                conditions_failed.append(condition.metric_name)
        
        # Apply logical operator to combine condition results
        triggered = self._apply_logical_operator(rule.logical_operator, condition_results)
        
        # Calculate severity score based on triggered conditions
        severity_score = 0.0
        if triggered:
            severity_score = sum(
                condition.weight for condition, met in zip(rule.conditions, condition_results) if met
            ) / len(rule.conditions)
        
        evaluation_time = time.time() - start_time
        
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            triggered=triggered,
            severity_score=severity_score,
            conditions_met=conditions_met,
            conditions_failed=conditions_failed,
            evaluation_time=evaluation_time
        )
    
    def _evaluate_condition(self, condition: ThresholdCondition, metrics: Dict[str, Any]) -> bool:
        """Evaluate a single threshold condition."""
        # Get metric value
        metric_value = self._get_metric_value(condition.metric_name, metrics)
        if metric_value is None:
            self.logger.debug(
                f"Metric {condition.metric_name} not found in current metrics",
                extra={"metric_name": condition.metric_name, "available_metrics": list(metrics.keys())}
            )
            return False
        
        # Apply threshold operator
        return self._apply_threshold_operator(condition.operator, metric_value, condition.value)
    
    def _get_metric_value(self, metric_name: str, metrics: Dict[str, Any]) -> Optional[float]:
        """Extract numeric metric value from metrics dictionary."""
        # Direct lookup
        if metric_name in metrics:
            value = metrics[metric_name]
            if isinstance(value, (int, float)):
                return float(value)
            elif isinstance(value, dict) and "value" in value:
                return float(value["value"])
        
        # Try common metric name variations
        variations = [
            metric_name.lower(),
            metric_name.upper(),
            metric_name.replace("_", "-"),
            metric_name.replace("-", "_"),
            f"{metric_name}_percent",
            f"{metric_name}_usage",
            f"{metric_name}_rate"
        ]
        
        for variation in variations:
            if variation in metrics:
                value = metrics[variation]
                if isinstance(value, (int, float)):
                    return float(value)
                elif isinstance(value, dict) and "value" in value:
                    return float(value["value"])
        
        return None
    
    def _apply_threshold_operator(
        self, 
        operator: ThresholdOperator, 
        metric_value: float, 
        threshold_value: Union[float, List[float]]
    ) -> bool:
        """Apply threshold operator to compare metric value with threshold."""
        if operator == ThresholdOperator.GREATER_THAN:
            return metric_value > threshold_value
        elif operator == ThresholdOperator.GREATER_EQUAL:
            return metric_value >= threshold_value
        elif operator == ThresholdOperator.LESS_THAN:
            return metric_value < threshold_value
        elif operator == ThresholdOperator.LESS_EQUAL:
            return metric_value <= threshold_value
        elif operator == ThresholdOperator.EQUAL:
            return abs(metric_value - threshold_value) < 1e-9  # Float comparison tolerance
        elif operator == ThresholdOperator.NOT_EQUAL:
            return abs(metric_value - threshold_value) >= 1e-9
        elif operator == ThresholdOperator.BETWEEN:
            if not isinstance(threshold_value, list) or len(threshold_value) != 2:
                raise ValueError("BETWEEN operator requires a list of exactly 2 values")
            return threshold_value[0] <= metric_value <= threshold_value[1]
        elif operator == ThresholdOperator.OUTSIDE:
            if not isinstance(threshold_value, list) or len(threshold_value) != 2:
                raise ValueError("OUTSIDE operator requires a list of exactly 2 values")
            return metric_value < threshold_value[0] or metric_value > threshold_value[1]
        else:
            raise ValueError(f"Unknown threshold operator: {operator}")
    
    def _apply_logical_operator(self, operator: LogicalOperator, results: List[bool]) -> bool:
        """Apply logical operator to combine condition results."""
        if not results:
            return False
        
        if operator == LogicalOperator.AND:
            return all(results)
        elif operator == LogicalOperator.OR:
            return any(results)
        elif operator == LogicalOperator.NOT:
            # NOT operator applies to the first result only
            return not results[0] if results else False
        else:
            raise ValueError(f"Unknown logical operator: {operator}")
    
    async def _generate_actions_from_rules(
        self, 
        triggered_rules: List[RuleEvaluationResult], 
        system_id: str,
        metrics: Dict[str, Any]
    ) -> List[AdaptationAction]:
        """Generate adaptation actions from triggered rules."""
        actions: List[AdaptationAction] = []
        
        # Sort rules by priority and severity if prioritization is enabled
        if self.config.action_prioritization_enabled:
            rule_priorities = []
            for result in triggered_rules:
                rule = next(r for r in self.config.rules if r.rule_id == result.rule_id)
                priority_score = rule.priority + result.severity_score
                rule_priorities.append((result, rule, priority_score))
            
            # Sort by priority score (descending)
            rule_priorities.sort(key=lambda x: x[2], reverse=True)
            sorted_rules = [(result, rule) for result, rule, _ in rule_priorities]
        else:
            sorted_rules = [
                (result, next(r for r in self.config.rules if r.rule_id == result.rule_id))
                for result in triggered_rules
            ]
        
        # Generate actions up to max concurrent limit
        for i, (result, rule) in enumerate(sorted_rules):
            if i >= self.config.max_concurrent_actions:
                self.logger.info(
                    f"Reached max concurrent actions limit ({self.config.max_concurrent_actions}), "
                    f"skipping remaining {len(sorted_rules) - i} rules"
                )
                break
            
            try:
                action = self._create_action_from_rule(rule, result, system_id, metrics)
                if action:
                    actions.append(action)
                    
            except Exception as e:
                self.logger.error(
                    f"Error creating action from rule {rule.rule_id}: {e}",
                    extra={"rule_id": rule.rule_id, "error": str(e)},
                    exc_info=True
                )
        
        return actions
    
    def _create_action_from_rule(
        self, 
        rule: ThresholdRule, 
        result: RuleEvaluationResult,
        system_id: str,
        metrics: Dict[str, Any]
    ) -> Optional[AdaptationAction]:
        """Create an adaptation action from a triggered rule."""
        if not rule.action_type:
            self.logger.warning(
                f"Rule {rule.rule_id} has no action_type defined",
                extra={"rule_id": rule.rule_id}
            )
            return None
        
        # Create action parameters by merging rule parameters with dynamic values
        action_parameters = rule.action_parameters.copy()
        
        # Add dynamic parameters based on current metrics and rule evaluation
        action_parameters.update({
            "triggered_conditions": result.conditions_met,
            "severity_score": result.severity_score,
            "rule_id": rule.rule_id,
            "evaluation_time": result.evaluation_time
        })
        
        # Create the adaptation action
        action = AdaptationAction(
            action_id=f"{rule.rule_id}_{int(time.time())}",
            action_type=rule.action_type,
            target_system=system_id,
            parameters=action_parameters,
            priority=rule.priority
        )
        
        self.logger.info(
            f"Created action from rule {rule.rule_id}",
            extra={
                "rule_id": rule.rule_id,
                "action_type": rule.action_type,
                "action_id": action.action_id,
                "severity_score": result.severity_score
            }
        )
        
        return action
    
    async def _fallback_generate_actions(
        self, 
        system_id: str, 
        current_state: Dict[str, Any],
        adaptation_need: AdaptationNeed
    ) -> List[AdaptationAction]:
        """Fallback to simple reactive behavior when threshold rules fail or don't trigger."""
        self.logger.info(
            f"Using fallback reactive strategy for system {system_id}",
            extra={"system_id": system_id, "adaptation_needed": adaptation_need.is_needed}
        )
        
        # Use simple reactive logic as fallback
        actions = []
        if adaptation_need.urgency > 0.7:
            actions.append(AdaptationAction(
                action_id=f"fallback_{system_id}_{int(time.time())}",
                action_type="ADD_SERVER",
                target_system=system_id,
                parameters={"reason": "fallback_high_urgency"},
                priority=2
            ))
        return actions


def _get_numeric_metric(metrics: Dict[str, Any], metric_names: List[str]) -> Optional[float]:
    """Helper function to extract numeric metric value from various possible keys."""
    for name in metric_names:
        if name in metrics:
            value = metrics[name]
            if isinstance(value, (int, float)):
                return float(value)
            elif isinstance(value, dict) and "value" in value:
                return float(value["value"])
    return None