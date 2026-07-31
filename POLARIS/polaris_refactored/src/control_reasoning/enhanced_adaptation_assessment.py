"""
Enhanced Adaptation Assessment

Improved adaptation need assessment that addresses current limitations:
- Trend analysis and pattern recognition
- Dynamic/adaptive thresholds
- Predictive assessment capabilities
- Multi-system correlation
- Learning-based threshold adaptation
"""

import time
import statistics
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from collections import deque, defaultdict
from enum import Enum

from ..domain.models import MetricValue
from ..framework.events import TelemetryEvent
from ..infrastructure.observability import get_logger, get_metrics_collector
from .adaptive_controller import AdaptationNeed


class TrendDirection(Enum):
    """Direction of metric trends."""
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"


class SeverityLevel(Enum):
    """Severity levels for adaptation needs."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class MetricTrend:
    """Represents trend analysis for a metric."""
    metric_name: str
    direction: TrendDirection
    rate_of_change: float  # per second
    confidence: float  # 0.0 to 1.0
    prediction_horizon: int  # seconds
    predicted_value: Optional[float] = None
    volatility: float = 0.0  # standard deviation


@dataclass
class AdaptiveThreshold:
    """Dynamic threshold that adapts based on historical performance."""
    metric_name: str
    current_high: float
    current_low: float
    baseline_high: float  # Original configured threshold
    baseline_low: float
    adaptation_factor: float = 0.1  # How quickly thresholds adapt
    confidence: float = 0.5  # Confidence in current thresholds
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    performance_history: List[float] = field(default_factory=list)


@dataclass
class SystemCorrelation:
    """Correlation between systems for multi-system analysis."""
    primary_system: str
    correlated_systems: List[str]
    correlation_strength: float  # -1.0 to 1.0
    lag_seconds: int  # Time lag between systems
    confidence: float


@dataclass
class EnhancedAdaptationNeed(AdaptationNeed):
    """Enhanced adaptation need with additional context."""
    trends: List[MetricTrend] = field(default_factory=list)
    predictions: Dict[str, float] = field(default_factory=dict)
    correlations: List[SystemCorrelation] = field(default_factory=list)
    severity: SeverityLevel = SeverityLevel.MEDIUM
    confidence: float = 0.5
    time_to_critical: Optional[int] = None  # seconds until critical state
    recommended_actions: List[str] = field(default_factory=list)


class MetricHistoryManager:
    """Manages historical metric data for trend analysis."""
    
    def __init__(self, max_history_minutes: int = 60):
        self.max_history_minutes = max_history_minutes
        self.metric_history: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
        self.logger = get_logger(self.__class__.__name__)
    
    def add_metric(self, system_id: str, metric_name: str, value: float, timestamp: datetime) -> None:
        """Add a metric value to history."""
        history = self.metric_history[system_id][metric_name]
        history.append((timestamp, value))
        
        # Clean old data
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=self.max_history_minutes)
        while history and history[0][0] < cutoff_time:
            history.popleft()
    
    def get_history(self, system_id: str, metric_name: str, minutes: int = 10) -> List[Tuple[datetime, float]]:
        """Get metric history for the specified time period."""
        history = self.metric_history[system_id][metric_name]
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return [(ts, val) for ts, val in history if ts >= cutoff_time]
    
    def get_recent_values(self, system_id: str, metric_name: str, count: int = 10) -> List[float]:
        """Get the most recent metric values."""
        history = self.metric_history[system_id][metric_name]
        return [val for _, val in list(history)[-count:]]


class TrendAnalyzer:
    """Analyzes metric trends and patterns."""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
    
    def analyze_trend(self, history: List[Tuple[datetime, float]], metric_name: str) -> MetricTrend:
        """Analyze trend for a metric based on historical data."""
        if len(history) < 3:
            return MetricTrend(
                metric_name=metric_name,
                direction=TrendDirection.STABLE,
                rate_of_change=0.0,
                confidence=0.0,
                prediction_horizon=0
            )
        
        # Extract values and timestamps
        timestamps = [ts.timestamp() for ts, _ in history]
        values = [val for _, val in history]
        
        # Calculate trend using linear regression
        n = len(values)
        sum_x = sum(timestamps)
        sum_y = sum(values)
        sum_xy = sum(t * v for t, v in zip(timestamps, values))
        sum_x2 = sum(t * t for t in timestamps)
        
        # Linear regression slope (rate of change per second)
        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            slope = 0
        else:
            slope = (n * sum_xy - sum_x * sum_y) / denominator
        
        # Determine trend direction
        if abs(slope) < 0.001:  # Very small change
            direction = TrendDirection.STABLE
        elif slope > 0:
            direction = TrendDirection.INCREASING
        else:
            direction = TrendDirection.DECREASING
        
        # Calculate volatility (standard deviation)
        volatility = statistics.stdev(values) if len(values) > 1 else 0.0
        
        # Determine if volatile
        mean_value = statistics.mean(values)
        if mean_value > 0 and volatility / mean_value > 0.2:  # 20% coefficient of variation
            direction = TrendDirection.VOLATILE
        
        # Calculate confidence based on R-squared
        if len(values) > 2:
            y_mean = sum_y / n
            ss_tot = sum((y - y_mean) ** 2 for y in values)
            ss_res = sum((values[i] - (slope * timestamps[i] + (sum_y - slope * sum_x) / n)) ** 2 
                        for i in range(n))
            confidence = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
            confidence = max(0.0, min(1.0, confidence))
        else:
            confidence = 0.0
        
        # Predict future value (30 seconds ahead)
        prediction_horizon = 30
        if confidence > 0.3:
            future_timestamp = timestamps[-1] + prediction_horizon
            intercept = (sum_y - slope * sum_x) / n
            predicted_value = slope * future_timestamp + intercept
        else:
            predicted_value = values[-1]  # Use current value if low confidence
        
        return MetricTrend(
            metric_name=metric_name,
            direction=direction,
            rate_of_change=slope,
            confidence=confidence,
            prediction_horizon=prediction_horizon,
            predicted_value=predicted_value,
            volatility=volatility
        )


class AdaptiveThresholdManager:
    """Manages dynamic thresholds that adapt based on system performance."""
    
    def __init__(self):
        self.thresholds: Dict[str, Dict[str, AdaptiveThreshold]] = defaultdict(dict)
        self.logger = get_logger(self.__class__.__name__)
        
        # Initialize default thresholds
        self._initialize_default_thresholds()
    
    def _initialize_default_thresholds(self) -> None:
        """Initialize default thresholds for common metrics."""
        default_thresholds = {
            "server_utilization": {"high": 0.8, "low": 0.2},
            "basic_response_time": {"high": 1000.0, "low": 100.0},
            "optional_response_time": {"high": 2000.0, "low": 200.0},
            "memory_usage": {"high": 0.85, "low": 0.3},
            "cpu_usage": {"high": 0.8, "low": 0.2}
        }
        
        for metric_name, thresholds in default_thresholds.items():
            self.thresholds["default"][metric_name] = AdaptiveThreshold(
                metric_name=metric_name,
                current_high=thresholds["high"],
                current_low=thresholds["low"],
                baseline_high=thresholds["high"],
                baseline_low=thresholds["low"]
            )
    
    def get_threshold(self, system_id: str, metric_name: str) -> AdaptiveThreshold:
        """Get adaptive threshold for a metric."""
        # Try system-specific threshold first
        if metric_name in self.thresholds[system_id]:
            return self.thresholds[system_id][metric_name]
        
        # Fall back to default threshold
        if metric_name in self.thresholds["default"]:
            # Create system-specific copy
            default_threshold = self.thresholds["default"][metric_name]
            self.thresholds[system_id][metric_name] = AdaptiveThreshold(
                metric_name=metric_name,
                current_high=default_threshold.current_high,
                current_low=default_threshold.current_low,
                baseline_high=default_threshold.baseline_high,
                baseline_low=default_threshold.baseline_low
            )
            return self.thresholds[system_id][metric_name]
        
        # Create new threshold with reasonable defaults
        self.thresholds[system_id][metric_name] = AdaptiveThreshold(
            metric_name=metric_name,
            current_high=1.0,
            current_low=0.0,
            baseline_high=1.0,
            baseline_low=0.0
        )
        return self.thresholds[system_id][metric_name]
    
    def update_threshold(self, system_id: str, metric_name: str, 
                        performance_outcome: str, metric_value: float) -> None:
        """Update threshold based on performance outcome."""
        threshold = self.get_threshold(system_id, metric_name)
        threshold.performance_history.append(metric_value)
        
        # Keep only recent history
        if len(threshold.performance_history) > 100:
            threshold.performance_history = threshold.performance_history[-50:]
        
        # Adapt thresholds based on performance
        if performance_outcome == "false_positive":
            # Threshold was too sensitive, relax it
            if metric_value > threshold.current_high:
                threshold.current_high += (metric_value - threshold.current_high) * threshold.adaptation_factor
            elif metric_value < threshold.current_low:
                threshold.current_low -= (threshold.current_low - metric_value) * threshold.adaptation_factor
        
        elif performance_outcome == "false_negative":
            # Threshold was not sensitive enough, tighten it
            if metric_value > threshold.baseline_high:
                threshold.current_high -= (threshold.current_high - threshold.baseline_high) * threshold.adaptation_factor
            elif metric_value < threshold.baseline_low:
                threshold.current_low += (threshold.baseline_low - threshold.current_low) * threshold.adaptation_factor
        
        # Update confidence based on recent performance
        if len(threshold.performance_history) >= 10:
            recent_variance = statistics.variance(threshold.performance_history[-10:])
            threshold.confidence = max(0.1, min(1.0, 1.0 / (1.0 + recent_variance)))
        
        threshold.last_updated = datetime.now(timezone.utc)


class EnhancedAdaptationAssessment:
    """Enhanced adaptation assessment with trend analysis, prediction, and learning."""
    
    def __init__(self, world_model=None, knowledge_base=None):
        self.world_model = world_model
        self.knowledge_base = knowledge_base
        self.history_manager = MetricHistoryManager()
        self.trend_analyzer = TrendAnalyzer()
        self.threshold_manager = AdaptiveThresholdManager()
        self.logger = get_logger(self.__class__.__name__)
        self.metrics = get_metrics_collector()
        
        # System correlation tracking
        self.system_correlations: Dict[str, List[SystemCorrelation]] = defaultdict(list)
        
        self.logger.info("Enhanced adaptation assessment initialized")
    
    async def assess_adaptation_need(self, telemetry: TelemetryEvent) -> EnhancedAdaptationNeed:
        """Enhanced adaptation need assessment with trend analysis and prediction."""
        system_state = telemetry.system_state
        system_id = system_state.system_id
        
        # Store metrics in history
        for metric_name, metric_value in system_state.metrics.items():
            self.history_manager.add_metric(
                system_id, metric_name, metric_value.value, system_state.timestamp
            )
        
        # Perform trend analysis
        trends = await self._analyze_trends(system_id, system_state.metrics)
        
        # Assess current state with adaptive thresholds
        current_assessment = await self._assess_current_state(system_id, system_state, trends)
        
        # Generate predictions
        predictions = await self._generate_predictions(system_id, trends)
        
        # Assess correlations with other systems
        correlations = await self._assess_system_correlations(system_id, system_state)
        
        # Calculate overall severity and urgency
        severity, urgency, confidence = self._calculate_severity_and_urgency(
            current_assessment, trends, predictions, correlations
        )
        
        # Determine time to critical state
        time_to_critical = self._calculate_time_to_critical(trends, predictions)
        
        # Generate recommended actions
        recommended_actions = self._generate_action_recommendations(
            current_assessment, trends, predictions, severity
        )
        
        # Create enhanced adaptation need
        enhanced_need = EnhancedAdaptationNeed(
            system_id=system_id,
            is_needed=current_assessment["is_needed"] or any(
                trend.direction == TrendDirection.INCREASING and trend.confidence > 0.5 
                for trend in trends if "utilization" in trend.metric_name or "response_time" in trend.metric_name
            ),
            reason=current_assessment["reason"],
            urgency=urgency,
            context={"telemetry": telemetry},
            trends=trends,
            predictions=predictions,
            correlations=correlations,
            severity=severity,
            confidence=confidence,
            time_to_critical=time_to_critical,
            recommended_actions=recommended_actions
        )
        
        # Log enhanced assessment
        self.logger.info(
            f"Enhanced assessment for {system_id}: {severity.value} severity, "
            f"{len(trends)} trends analyzed, {confidence:.2f} confidence",
            extra={
                "system_id": system_id,
                "severity": severity.value,
                "urgency": urgency,
                "trends_count": len(trends),
                "predictions_count": len(predictions),
                "time_to_critical": time_to_critical
            }
        )
        
        return enhanced_need
    
    async def _analyze_trends(self, system_id: str, metrics: Dict[str, MetricValue]) -> List[MetricTrend]:
        """Analyze trends for all metrics."""
        trends = []
        
        for metric_name in metrics.keys():
            history = self.history_manager.get_history(system_id, metric_name, minutes=10)
            if len(history) >= 3:
                trend = self.trend_analyzer.analyze_trend(history, metric_name)
                trends.append(trend)
        
        return trends
    
    async def _assess_current_state(self, system_id: str, system_state, trends: List[MetricTrend]) -> Dict[str, Any]:
        """Assess current state using adaptive thresholds."""
        is_needed = False
        reasons = []
        urgency = 0.0
        
        # Health status check (unchanged)
        if system_state.health_status.value in ["warning", "critical", "unhealthy"]:
            is_needed = True
            reasons.append(f"System health is {system_state.health_status.value}")
            urgency = max(urgency, 0.7 if system_state.health_status.value == "warning" else 0.9)
        
        # Adaptive threshold checks
        for metric_name, metric_value in system_state.metrics.items():
            threshold = self.threshold_manager.get_threshold(system_id, metric_name)
            value = metric_value.value
            
            if value > threshold.current_high:
                is_needed = True
                reasons.append(f"High {metric_name}: {value:.3f} > {threshold.current_high:.3f}")
                urgency = max(urgency, 0.8)
            elif value < threshold.current_low:
                is_needed = True
                reasons.append(f"Low {metric_name}: {value:.3f} < {threshold.current_low:.3f}")
                urgency = max(urgency, 0.4)
        
        # Trend-based assessment
        for trend in trends:
            if trend.confidence > 0.6:
                if trend.direction == TrendDirection.INCREASING and "utilization" in trend.metric_name:
                    if trend.predicted_value and trend.predicted_value > 0.9:
                        is_needed = True
                        reasons.append(f"Predicted high {trend.metric_name}: {trend.predicted_value:.3f}")
                        urgency = max(urgency, 0.7)
                elif trend.direction == TrendDirection.VOLATILE:
                    urgency = max(urgency, 0.5)
                    reasons.append(f"Volatile {trend.metric_name} (σ={trend.volatility:.3f})")
        
        return {
            "is_needed": is_needed,
            "reason": "; ".join(reasons) if reasons else "No adaptation needed",
            "urgency": urgency
        }
    
    async def _generate_predictions(self, system_id: str, trends: List[MetricTrend]) -> Dict[str, float]:
        """Generate predictions for key metrics."""
        predictions = {}
        
        for trend in trends:
            if trend.confidence > 0.4 and trend.predicted_value is not None:
                predictions[f"{trend.metric_name}_30s"] = trend.predicted_value
        
        return predictions
    
    async def _assess_system_correlations(self, system_id: str, system_state) -> List[SystemCorrelation]:
        """Assess correlations with other systems (placeholder for future implementation)."""
        # This would analyze correlations between systems
        # For now, return empty list
        return []
    
    def _calculate_severity_and_urgency(self, current_assessment: Dict[str, Any], 
                                      trends: List[MetricTrend], predictions: Dict[str, float],
                                      correlations: List[SystemCorrelation]) -> Tuple[SeverityLevel, float, float]:
        """Calculate overall severity, urgency, and confidence."""
        base_urgency = current_assessment["urgency"]
        
        # Adjust urgency based on trends
        trend_urgency = 0.0
        for trend in trends:
            if trend.confidence > 0.5:
                if trend.direction == TrendDirection.INCREASING:
                    trend_urgency = max(trend_urgency, 0.6)
                elif trend.direction == TrendDirection.VOLATILE:
                    trend_urgency = max(trend_urgency, 0.4)
        
        # Adjust urgency based on predictions
        prediction_urgency = 0.0
        for metric_name, predicted_value in predictions.items():
            if "utilization" in metric_name and predicted_value > 0.9:
                prediction_urgency = max(prediction_urgency, 0.8)
            elif "response_time" in metric_name and predicted_value > 2000:
                prediction_urgency = max(prediction_urgency, 0.7)
        
        # Combined urgency
        final_urgency = max(base_urgency, trend_urgency, prediction_urgency)
        
        # Determine severity
        if final_urgency >= 0.9:
            severity = SeverityLevel.CRITICAL
        elif final_urgency >= 0.7:
            severity = SeverityLevel.HIGH
        elif final_urgency >= 0.4:
            severity = SeverityLevel.MEDIUM
        else:
            severity = SeverityLevel.LOW
        
        # Calculate confidence based on trend confidence
        avg_confidence = statistics.mean([t.confidence for t in trends]) if trends else 0.5
        
        return severity, final_urgency, avg_confidence
    
    def _calculate_time_to_critical(self, trends: List[MetricTrend], predictions: Dict[str, float]) -> Optional[int]:
        """Calculate estimated time until critical state is reached."""
        min_time_to_critical = None
        
        for trend in trends:
            if trend.confidence > 0.5 and trend.rate_of_change > 0:
                if "utilization" in trend.metric_name:
                    # Calculate time to reach 95% utilization
                    current_value = trend.predicted_value or 0.5
                    if current_value < 0.95:
                        time_to_critical = (0.95 - current_value) / trend.rate_of_change
                        if time_to_critical > 0:
                            min_time_to_critical = min(min_time_to_critical or float('inf'), int(time_to_critical))
        
        return min_time_to_critical
    
    def _generate_action_recommendations(self, current_assessment: Dict[str, Any], 
                                       trends: List[MetricTrend], predictions: Dict[str, float],
                                       severity: SeverityLevel) -> List[str]:
        """Generate recommended actions based on assessment."""
        recommendations = []
        
        if severity == SeverityLevel.CRITICAL:
            recommendations.append("immediate_scale_up")
            recommendations.append("enable_circuit_breaker")
        elif severity == SeverityLevel.HIGH:
            recommendations.append("scale_up")
            recommendations.append("adjust_qos")
        elif severity == SeverityLevel.MEDIUM:
            recommendations.append("monitor_closely")
            
        # Trend-based recommendations
        for trend in trends:
            if trend.confidence > 0.6:
                if trend.direction == TrendDirection.INCREASING and "utilization" in trend.metric_name:
                    recommendations.append("proactive_scale_up")
                elif trend.direction == TrendDirection.VOLATILE:
                    recommendations.append("stabilize_workload")
        
        return list(set(recommendations))  # Remove duplicates
    
    def update_performance_feedback(self, system_id: str, metric_name: str, 
                                  outcome: str, metric_value: float) -> None:
        """Update thresholds based on performance feedback."""
        self.threshold_manager.update_threshold(system_id, metric_name, outcome, metric_value)
        
        self.logger.debug(f"Updated threshold for {system_id}.{metric_name} based on {outcome}")