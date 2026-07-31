"""
Example implementation of the Meta-Learner Agent inter        super().__init__(agent_id, logger, config)

        self.kb_client = knowledge_base_client
        self.world_model_client = world_model_client

        # Learning state
        self.learning_history: List[Dict[str, Any]] = []
        self.last_analysis_time: Optional[datetime] = None
        self.last_calibration_time: Optional[datetime] = None
        self.applied_updates_count = 0

        # Configuration defaults
        self.min_confidence_threshold = self.config.get("min_confidence_threshold", 0.7)
        self.analysis_window_hours = self.config.get("analysis_window_hours", 24.0)
        self.calibration_frequency_hours = self.config.get("calibration_frequency_hours", 6.0)ule provides a concrete example of how to implement the BaseMetaLearnerAgent
interface, demonstrating the key patterns and interactions for meta-level learning
in the POLARIS framework.

This is a simplified implementation for demonstration and testing purposes.
Production implementations would use more sophisticated machine learning approaches.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .meta_learner_agent import (
    BaseMetaLearnerAgent,
    TriggerType,
    ParameterType,
    MetaLearningContext,
    ParameterUpdate,
    CalibrationRequest,
    CalibrationResult,
    MetaLearningInsights,
    MetaLearningError,
    CalibrationError,
    ParameterUpdateError,
    ValidationError,
    UpdateApplicationError,
)


class ExampleMetaLearnerAgent(BaseMetaLearnerAgent):
    """
    Example implementation of a Meta-Learner agent using simple heuristics.

    This implementation demonstrates the interface usage with basic learning
    strategies that could be extended with more sophisticated ML approaches.
    """

    def __init__(
        self,
        agent_id: str,
        config_path: str,
        nats_url: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize the example meta-learner agent.

        Args:
            agent_id: Unique identifier for this agent
            config_path: Path to POLARIS framework configuration
            nats_url: NATS server URL (loaded from config if not provided)
            logger: Logger instance
            config: Agent configuration
        """
        super().__init__(agent_id, config_path, nats_url, logger, config)

        # Learning state
        self.learning_history: List[Dict[str, Any]] = []
        self.last_analysis_time: Optional[datetime] = None
        self.last_calibration_time: Optional[datetime] = None
        self.applied_updates_count = 0

        # Configuration defaults
        self.min_confidence_threshold = self.config.get("min_confidence_threshold", 0.7)
        self.analysis_window_hours = self.config.get("analysis_window_hours", 24.0)
        self.calibration_frequency_hours = self.config.get(
            "calibration_frequency_hours", 6.0
        )

    async def analyze_adaptation_patterns(
        self, context: MetaLearningContext
    ) -> MetaLearningInsights:
        """Analyze adaptation patterns from the knowledge base."""
        try:
            self.logger.info(
                f"Starting pattern analysis with context: {context.trigger_type}"
            )

            # Simulate knowledge base query for adaptation decisions
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=context.time_window_hours)

            # In a real implementation, this would query the knowledge base
            # for adaptation decisions, system metrics, and performance data
            adaptation_patterns = await self._query_adaptation_patterns(
                start_time, end_time
            )
            performance_trends = await self._analyze_performance_trends(
                start_time, end_time
            )
            coordination_effectiveness = (
                await self._evaluate_coordination_effectiveness(start_time, end_time)
            )

            # Generate insights based on analysis
            insights = MetaLearningInsights(
                analysis_window={"start": start_time, "end": end_time},
                adaptation_patterns=adaptation_patterns,
                performance_trends=performance_trends,
                coordination_effectiveness=coordination_effectiveness,
                recommendations=self._generate_recommendations(
                    adaptation_patterns, performance_trends, coordination_effectiveness
                ),
                confidence_overall=self._calculate_overall_confidence(
                    adaptation_patterns, performance_trends
                ),
            )

            self.last_analysis_time = datetime.now(timezone.utc)
            self.logger.info(
                f"Pattern analysis completed with confidence: {insights.confidence_overall}"
            )

            return insights

        except Exception as e:
            self.logger.error(f"Pattern analysis failed: {e}")
            raise MetaLearningError(f"Failed to analyze adaptation patterns: {e}")

    async def calibrate_world_model(
        self, calibration_request: CalibrationRequest
    ) -> CalibrationResult:
        """Calibrate the world model using historical data."""
        try:
            self.logger.info(
                f"Starting world model calibration: {calibration_request.request_id}"
            )

            # Try to use Digital Twin for calibration
            dt_response = None
            try:
                dt_response = await self.request_world_model_calibration(
                    calibration_request.target_metrics,
                    calibration_request.validation_window_hours,
                )
            except RuntimeError as e:
                if "Not connected to NATS" in str(e):
                    self.logger.warning(
                        "Digital Twin calibration not available, using mock calibration"
                    )
                else:
                    raise

            if dt_response and dt_response.success:
                # Real calibration from Digital Twin
                result = CalibrationResult(
                    request_id=calibration_request.request_id,
                    success=True,
                    improvement_score=dt_response.confidence,
                    calibrated_parameters=dt_response.metadata.get(
                        "calibrated_parameters", {}
                    ),
                    validation_metrics=dt_response.calibration_metrics,
                )
            else:
                # Fallback to mock calibration if DT unavailable
                self.logger.warning(
                    "Digital Twin calibration failed, using mock calibration"
                )

                # Simulate calibration process
                await asyncio.sleep(0.1)  # Simulate processing time

                # Extract historical data for comparison
                target_metrics = calibration_request.target_metrics

                # Calculate improvement score based on mock validation
                improvement_score = min(0.95, 0.7 + len(target_metrics) * 0.05)

                result = CalibrationResult(
                    request_id=calibration_request.request_id,
                    success=True,
                    improvement_score=improvement_score,
                    calibrated_parameters={
                        "learning_rate": 0.01,
                        "regularization": 0.001,
                        "ensemble_weights": [0.3, 0.4, 0.3],
                    },
                    validation_metrics={
                        metric: 0.85 + (hash(metric) % 15) / 100
                        for metric in target_metrics
                    },
                )

            self.last_calibration_time = datetime.now(timezone.utc)
            self.logger.info(
                f"Calibration completed with improvement: {result.improvement_score}"
            )

            return result

        except Exception as e:
            self.logger.error(f"World model calibration failed: {e}")
            raise CalibrationError(f"Failed to calibrate world model: {e}")

    async def propose_parameter_updates(
        self, insights: MetaLearningInsights, context: MetaLearningContext
    ) -> List[ParameterUpdate]:
        """Propose parameter updates based on insights."""
        try:
            self.logger.info("Generating parameter update proposals")

            proposed_updates = []

            # Analyze performance trends to propose utility weight updates
            performance_trends = insights.performance_trends
            if "response_time" in performance_trends:
                trend_value = performance_trends["response_time"]
                if trend_value > 1.1:  # Performance degrading
                    proposed_updates.append(
                        ParameterUpdate(
                            parameter_type=ParameterType.UTILITY_WEIGHTS,
                            parameter_path="coordinator.utility.performance",
                            old_value=0.5,
                            new_value=0.6,
                            confidence=min(0.9, 0.7 + abs(trend_value - 1.0)),
                            reasoning=f"Response time trend shows {trend_value:.2f}x degradation, increasing performance weight",
                            expected_impact="Faster adaptation responses, potentially higher resource usage",
                            risk_assessment="Low risk - conservative weight adjustment",
                        )
                    )

            # Analyze coordination effectiveness for strategy updates
            coord_effectiveness = insights.coordination_effectiveness
            if "auction_success_rate" in coord_effectiveness:
                success_rate = coord_effectiveness["auction_success_rate"]
                if success_rate < 0.8:  # Low coordination success
                    proposed_updates.append(
                        ParameterUpdate(
                            parameter_type=ParameterType.COORDINATION_STRATEGIES,
                            parameter_path="coordinator.auction.timeout_ms",
                            old_value=5000,
                            new_value=7500,
                            confidence=0.8,
                            reasoning=f"Auction success rate is {success_rate:.2f}, increasing timeout for better coordination",
                            expected_impact="Higher coordination success rate, slightly slower decisions",
                            risk_assessment="Low risk - timeout adjustment with proven benefits",
                        )
                    )

            # Analyze adaptation patterns for policy parameter updates
            adaptation_patterns = insights.adaptation_patterns
            if len(adaptation_patterns) > 0:
                avg_adaptation_time = sum(
                    pattern.get("execution_time_ms", 1000)
                    for pattern in adaptation_patterns
                ) / len(adaptation_patterns)

                if avg_adaptation_time > 2000:  # Slow adaptations
                    proposed_updates.append(
                        ParameterUpdate(
                            parameter_type=ParameterType.POLICY_PARAMETERS,
                            parameter_path="fast_control.response_threshold",
                            old_value=0.8,
                            new_value=0.7,
                            confidence=0.75,
                            reasoning=f"Average adaptation time is {avg_adaptation_time:.0f}ms, lowering threshold for faster response",
                            expected_impact="Faster initial response, potentially more frequent adaptations",
                            risk_assessment="Medium risk - may increase adaptation noise",
                        )
                    )

            # Filter updates by minimum confidence threshold
            filtered_updates = [
                update
                for update in proposed_updates
                if update.confidence >= self.min_confidence_threshold
            ]

            self.logger.info(
                f"Generated {len(filtered_updates)} parameter updates (filtered from {len(proposed_updates)})"
            )
            return filtered_updates

        except Exception as e:
            self.logger.error(f"Parameter update generation failed: {e}")
            raise ParameterUpdateError(f"Failed to generate parameter updates: {e}")

    async def validate_updates(
        self,
        proposed_updates: List[ParameterUpdate],
        validation_context: Optional[Dict[str, Any]] = None,
    ) -> List[ParameterUpdate]:
        """Validate proposed parameter updates."""
        try:
            self.logger.info(f"Validating {len(proposed_updates)} parameter updates")

            validated_updates = []

            for update in proposed_updates:
                # Perform safety checks
                if self._is_safe_update(update, validation_context):
                    # Adjust confidence based on validation results
                    validation_confidence = self._calculate_validation_confidence(
                        update
                    )
                    update.confidence = min(update.confidence, validation_confidence)

                    if update.confidence >= self.min_confidence_threshold:
                        validated_updates.append(update)
                        self.logger.debug(f"Update validated: {update.parameter_path}")
                    else:
                        self.logger.info(
                            f"Update rejected due to low confidence: {update.parameter_path}"
                        )
                else:
                    self.logger.warning(
                        f"Update failed safety check: {update.parameter_path}"
                    )

            self.logger.info(
                f"Validated {len(validated_updates)} updates out of {len(proposed_updates)}"
            )
            return validated_updates

        except Exception as e:
            self.logger.error(f"Update validation failed: {e}")
            raise ValidationError(f"Failed to validate parameter updates: {e}")

    async def apply_updates(
        self, validated_updates: List[ParameterUpdate]
    ) -> Dict[str, bool]:
        """Apply validated parameter updates."""
        try:
            self.logger.info(f"Applying {len(validated_updates)} parameter updates")

            results = {}

            for update in validated_updates:
                try:
                    # In a real implementation, this would interact with the
                    # appropriate system components to apply the parameter changes
                    success = await self._apply_single_update(update)
                    results[update.update_id] = success

                    if success:
                        self.applied_updates_count += 1
                        self.learning_history.append(
                            {
                                "timestamp": datetime.now(timezone.utc),
                                "action": "parameter_update",
                                "update_id": update.update_id,
                                "parameter_path": update.parameter_path,
                                "confidence": update.confidence,
                            }
                        )
                        self.logger.debug(
                            f"Successfully applied update: {update.parameter_path}"
                        )
                    else:
                        self.logger.warning(
                            f"Failed to apply update: {update.parameter_path}"
                        )

                except Exception as e:
                    self.logger.error(f"Error applying update {update.update_id}: {e}")
                    results[update.update_id] = False

            success_count = sum(results.values())
            self.logger.info(
                f"Applied {success_count}/{len(validated_updates)} updates successfully"
            )

            return results

        except Exception as e:
            self.logger.error(f"Update application failed: {e}")
            raise UpdateApplicationError(f"Failed to apply parameter updates: {e}")

    async def handle_trigger(
        self, trigger_type: TriggerType, trigger_data: Dict[str, Any]
    ) -> bool:
        """Handle different types of meta-learning triggers."""
        try:
            self.logger.info(f"Handling trigger: {trigger_type}")

            # Create context based on trigger type
            context = MetaLearningContext(
                trigger_type=trigger_type,
                trigger_source=trigger_data.get("source", "unknown"),
                time_window_hours=trigger_data.get(
                    "time_window_hours", self.analysis_window_hours
                ),
                focus_areas=trigger_data.get("focus_areas", []),
                constraints=trigger_data.get("constraints", {}),
                metadata=trigger_data.get("metadata", {}),
            )

            # Execute meta-learning cycle based on trigger type
            if trigger_type == TriggerType.PERIODIC:
                return await self._handle_periodic_trigger(context)
            elif trigger_type == TriggerType.PERFORMANCE_DRIVEN:
                return await self._handle_performance_trigger(context)
            elif trigger_type == TriggerType.THRESHOLD_VIOLATION:
                return await self._handle_threshold_trigger(context)
            elif trigger_type == TriggerType.EVENT_DRIVEN:
                return await self._handle_event_trigger(context)
            else:
                self.logger.warning(f"Unknown trigger type: {trigger_type}")
                return False

        except Exception as e:
            self.logger.error(f"Trigger handling failed: {e}")
            return False

    # Helper methods

    async def _query_adaptation_patterns(
        self, start_time: datetime, end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Query adaptation patterns from knowledge base."""
        try:
            # Use base class method to query adaptation patterns
            time_window_hours = (end_time - start_time).total_seconds() / 3600
            patterns = await self.query_adaptation_patterns(time_window_hours, limit=50)

            if patterns:
                # Process real patterns from KB
                processed_patterns = []
                for pattern in patterns:
                    processed_patterns.append(
                        {
                            "pattern_type": pattern.get("summary", "unknown"),
                            "frequency": pattern.get("content", {}).get("frequency", 1),
                            "success_rate": pattern.get("content", {}).get(
                                "success_rate", 0.5
                            ),
                            "avg_execution_time_ms": pattern.get("content", {}).get(
                                "execution_time_ms", 1000
                            ),
                            "context": (
                                pattern.get("tags", ["unknown"])[0]
                                if pattern.get("tags")
                                else "unknown"
                            ),
                        }
                    )
                return processed_patterns
            else:
                # Fallback to mock data if no real patterns available
                return [
                    {
                        "pattern_type": "scale_out",
                        "frequency": 12,
                        "success_rate": 0.92,
                        "avg_execution_time_ms": 1500,
                        "context": "high_cpu_utilization",
                    },
                    {
                        "pattern_type": "circuit_breaker",
                        "frequency": 3,
                        "success_rate": 0.85,
                        "avg_execution_time_ms": 800,
                        "context": "external_service_failure",
                    },
                ]
        except Exception as e:
            self.logger.warning(
                f"Failed to query adaptation patterns: {e}, using mock data"
            )
            # Return mock data as fallback
            return [
                {
                    "pattern_type": "scale_out",
                    "frequency": 12,
                    "success_rate": 0.92,
                    "avg_execution_time_ms": 1500,
                    "context": "high_cpu_utilization",
                },
            ]

    async def _analyze_performance_trends(
        self, start_time: datetime, end_time: datetime
    ) -> Dict[str, float]:
        """Analyze performance trends from metrics."""
        try:
            # Use base class method to query performance trends
            time_window_hours = (end_time - start_time).total_seconds() / 3600
            trends = await self.query_performance_trends(time_window_hours, limit=30)

            if trends:
                # Process real trends from KB
                trend_metrics = {}
                for trend in trends:
                    metric_name = trend.get("metric_name", "unknown")
                    metric_value = trend.get("metric_value", 1.0)

                    if "response_time" in metric_name.lower():
                        trend_metrics["response_time"] = float(metric_value)
                    elif "throughput" in metric_name.lower():
                        trend_metrics["throughput"] = float(metric_value)
                    elif "error" in metric_name.lower():
                        trend_metrics["error_rate"] = float(metric_value)
                    elif (
                        "cpu" in metric_name.lower() or "memory" in metric_name.lower()
                    ):
                        trend_metrics["resource_utilization"] = float(metric_value)

                # Fill in missing metrics with defaults
                return {
                    "response_time": trend_metrics.get("response_time", 1.0),
                    "throughput": trend_metrics.get("throughput", 1.0),
                    "error_rate": trend_metrics.get("error_rate", 1.0),
                    "resource_utilization": trend_metrics.get(
                        "resource_utilization", 1.0
                    ),
                }
            else:
                # Fallback to mock data
                return {
                    "response_time": 1.15,  # 15% increase
                    "throughput": 0.95,  # 5% decrease
                    "error_rate": 1.05,  # 5% increase
                    "resource_utilization": 1.08,  # 8% increase
                }
        except Exception as e:
            self.logger.warning(
                f"Failed to analyze performance trends: {e}, using mock data"
            )
            return {
                "response_time": 1.15,
                "throughput": 0.95,
                "error_rate": 1.05,
                "resource_utilization": 1.08,
            }

    async def _evaluate_coordination_effectiveness(
        self, start_time: datetime, end_time: datetime
    ) -> Dict[str, float]:
        """Evaluate coordination mechanism effectiveness."""
        # Mock implementation - would analyze coordination events
        return {
            "auction_success_rate": 0.88,
            "consensus_time_ms": 250,
            "conflict_resolution_rate": 0.94,
            "agent_participation_rate": 0.91,
        }

    def _generate_recommendations(
        self,
        patterns: List[Dict[str, Any]],
        trends: Dict[str, float],
        coordination: Dict[str, float],
    ) -> List[str]:
        """Generate human-readable recommendations."""
        recommendations = []

        if trends.get("response_time", 1.0) > 1.1:
            recommendations.append(
                "Consider increasing performance weight in utility function"
            )

        if coordination.get("auction_success_rate", 1.0) < 0.85:
            recommendations.append(
                "Evaluate auction timeout and participation thresholds"
            )

        if len(patterns) > 0:
            avg_success = sum(p.get("success_rate", 0) for p in patterns) / len(
                patterns
            )
            if avg_success < 0.9:
                recommendations.append(
                    "Review adaptation strategy effectiveness and error handling"
                )

        return recommendations

    def _calculate_overall_confidence(
        self, patterns: List[Dict[str, Any]], trends: Dict[str, float]
    ) -> float:
        """Calculate overall confidence in insights."""
        # Simple heuristic based on data quality and consistency
        pattern_confidence = min(
            1.0, len(patterns) / 5.0
        )  # More patterns = higher confidence
        trend_confidence = 0.9 if len(trends) >= 3 else 0.7  # Sufficient metrics

        return (pattern_confidence + trend_confidence) / 2.0

    def _is_safe_update(
        self, update: ParameterUpdate, context: Optional[Dict[str, Any]]
    ) -> bool:
        """Check if parameter update is safe to apply."""
        # Basic safety checks
        if update.confidence < 0.5:
            return False

        # Check for reasonable value ranges
        if update.parameter_type == ParameterType.UTILITY_WEIGHTS:
            if not (0.0 <= update.new_value <= 1.0):
                return False

        # Check constraints from context
        if context and "forbidden_parameters" in context:
            if update.parameter_path in context["forbidden_parameters"]:
                return False

        return True

    def _calculate_validation_confidence(self, update: ParameterUpdate) -> float:
        """Calculate confidence adjustment based on validation."""
        # Simple validation confidence calculation
        base_confidence = 0.9

        # Reduce confidence for larger changes
        if hasattr(update.old_value, "__sub__") and hasattr(
            update.new_value, "__sub__"
        ):
            try:
                change_magnitude = abs(update.new_value - update.old_value) / abs(
                    update.old_value
                )
                if change_magnitude > 0.5:  # Large change
                    base_confidence *= 0.8
            except (TypeError, ZeroDivisionError):
                pass

        return base_confidence

    async def _apply_single_update(self, update: ParameterUpdate) -> bool:
        """Apply a single parameter update."""
        # Mock implementation - would interact with actual system components
        await asyncio.sleep(0.05)  # Simulate update time

        # Simulate occasional failures
        import random

        return random.random() > 0.1  # 90% success rate

    async def _handle_periodic_trigger(self, context: MetaLearningContext) -> bool:
        """Handle periodic meta-learning trigger."""
        # Full meta-learning cycle
        insights = await self.analyze_adaptation_patterns(context)

        # Store insights in knowledge base
        await self.store_meta_learning_insights(insights)

        updates = await self.propose_parameter_updates(insights, context)
        validated = await self.validate_updates(updates)
        results = await self.apply_updates(validated)

        return len(results) > 0 and any(results.values())

    async def _handle_performance_trigger(self, context: MetaLearningContext) -> bool:
        """Handle performance-driven trigger."""
        # Focus on performance-related adjustments
        context.focus_areas = ["performance", "response_time", "throughput"]
        return await self._handle_periodic_trigger(context)

    async def _handle_threshold_trigger(self, context: MetaLearningContext) -> bool:
        """Handle threshold violation trigger."""
        # Quick analysis and targeted updates
        insights = await self.analyze_adaptation_patterns(context)

        # Store insights in knowledge base
        await self.store_meta_learning_insights(insights)

        updates = await self.propose_parameter_updates(insights, context)

        # Filter to only threshold-related updates
        threshold_updates = [
            u
            for u in updates
            if u.parameter_type
            in [ParameterType.THRESHOLD_VALUES, ParameterType.CONTROL_GAINS]
        ]

        validated = await self.validate_updates(threshold_updates)
        results = await self.apply_updates(validated)

        return len(results) > 0 and any(results.values())

    async def _handle_event_trigger(self, context: MetaLearningContext) -> bool:
        """Handle event-driven trigger."""
        # Analyze specific event patterns
        return await self._handle_periodic_trigger(context)
