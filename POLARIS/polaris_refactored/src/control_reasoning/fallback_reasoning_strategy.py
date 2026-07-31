"""
Fallback Reasoning Strategy with LLM Integration

Implements a robust reasoning strategy that uses LLM-based agentic reasoning
as the primary approach with fallback to existing statistical and causal
reasoning strategies when LLM operations fail.
"""

import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timezone

from .reasoning_engine import (
    ReasoningStrategy, ReasoningContext, ReasoningResult,
    StatisticalReasoningStrategy, CausalReasoningStrategy
)
from .agentic_llm_reasoning_strategy import AgenticLLMReasoningStrategy
from ..infrastructure.llm.client import LLMClient
from ..infrastructure.llm.exceptions import LLMAPIError, LLMTimeoutError, LLMRateLimitError
from ..infrastructure.observability.factory import get_control_logger
from ..digital_twin.world_model import PolarisWorldModel
from ..digital_twin.knowledge_base import PolarisKnowledgeBase


class FallbackReasoningStrategy(ReasoningStrategy):
    """
    Reasoning strategy with intelligent fallback mechanisms.
    
    This strategy implements a hierarchical approach to reasoning:
    1. Primary: Agentic LLM reasoning for sophisticated analysis
    2. Secondary: Causal reasoning for dependency-based analysis
    3. Tertiary: Statistical reasoning for basic anomaly detection
    
    The strategy automatically falls back to simpler approaches when:
    - LLM API is unavailable or rate-limited
    - LLM responses are invalid or low-confidence
    - Network connectivity issues occur
    - Timeout conditions are met
    
    Features:
    - Automatic fallback detection and switching
    - Confidence-based strategy selection
    - Performance monitoring and adaptive thresholds
    - Comprehensive error handling and recovery
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        world_model: PolarisWorldModel,
        knowledge_base: PolarisKnowledgeBase,
        enable_llm_fallback: bool = True,
        llm_confidence_threshold: float = 0.5,
        llm_timeout_seconds: float = 30.0,
        max_llm_retries: int = 2
    ):
        self.llm_client = llm_client
        self.world_model = world_model
        self.knowledge_base = knowledge_base
        self.enable_llm_fallback = enable_llm_fallback
        self.llm_confidence_threshold = llm_confidence_threshold
        self.llm_timeout_seconds = llm_timeout_seconds
        self.max_llm_retries = max_llm_retries
        
        # Initialize reasoning strategies
        self.agentic_strategy = AgenticLLMReasoningStrategy(
            llm_client=llm_client,
            world_model=world_model,
            knowledge_base=knowledge_base,
            max_iterations=8,  # Reduced for fallback scenario
            confidence_threshold=llm_confidence_threshold
        )
        
        self.causal_strategy = CausalReasoningStrategy(knowledge_base=knowledge_base)
        self.statistical_strategy = StatisticalReasoningStrategy(knowledge_base=knowledge_base)
        
        # Performance tracking
        self.strategy_performance = {
            "agentic_llm": {"attempts": 0, "successes": 0, "avg_confidence": 0.0},
            "causal": {"attempts": 0, "successes": 0, "avg_confidence": 0.0},
            "statistical": {"attempts": 0, "successes": 0, "avg_confidence": 0.0}
        }
        
        # Setup logging
        self.logger = get_control_logger("fallback_reasoning_strategy")
    
    async def reason(self, context: ReasoningContext) -> ReasoningResult:
        """
        Perform reasoning with intelligent fallback mechanisms.
        
        Args:
            context: Reasoning context with system information
            
        Returns:
            ReasoningResult from the most appropriate strategy
        """
        reasoning_attempts = []
        final_result = None
        
        # Strategy execution order with fallback logic
        strategies_to_try = [
            ("agentic_llm", self._try_agentic_reasoning),
            ("causal", self._try_causal_reasoning),
            ("statistical", self._try_statistical_reasoning)
        ]
        
        for strategy_name, strategy_func in strategies_to_try:
            try:
                self.logger.info(f"Attempting reasoning with {strategy_name} strategy")
                
                # Track attempt
                self.strategy_performance[strategy_name]["attempts"] += 1
                
                # Execute strategy
                result = await strategy_func(context)
                
                # Validate result
                if self._is_valid_result(result, strategy_name):
                    # Update performance tracking
                    self.strategy_performance[strategy_name]["successes"] += 1
                    self._update_confidence_tracking(strategy_name, result.confidence)
                    
                    # Add strategy metadata to result
                    result = self._enhance_result_with_metadata(
                        result, strategy_name, reasoning_attempts
                    )
                    
                    final_result = result
                    self.logger.info(f"Successfully completed reasoning with {strategy_name} strategy")
                    break
                else:
                    self.logger.warning(f"{strategy_name} strategy produced invalid result")
                    reasoning_attempts.append({
                        "strategy": strategy_name,
                        "status": "invalid_result",
                        "confidence": result.confidence if result else 0.0
                    })
            
            except Exception as e:
                self.logger.error(f"{strategy_name} strategy failed: {str(e)}")
                reasoning_attempts.append({
                    "strategy": strategy_name,
                    "status": "error",
                    "error": str(e),
                    "error_type": type(e).__name__
                })
                
                # For LLM-specific errors, decide whether to continue fallback
                if strategy_name == "agentic_llm" and not self._should_continue_fallback(e):
                    self.logger.info("LLM error indicates temporary issue, skipping further fallback")
                    break
        
        # If no strategy succeeded, create emergency fallback result
        if final_result is None:
            final_result = self._create_emergency_fallback_result(context, reasoning_attempts)
        
        return final_result
    
    async def _try_agentic_reasoning(self, context: ReasoningContext) -> ReasoningResult:
        """Attempt agentic LLM reasoning with timeout and retry logic."""
        
        if not self.enable_llm_fallback:
            raise RuntimeError("LLM fallback is disabled")
        
        last_exception = None
        
        for attempt in range(self.max_llm_retries + 1):
            try:
                # Add timeout wrapper
                import asyncio
                result = await asyncio.wait_for(
                    self.agentic_strategy.reason(context),
                    timeout=self.llm_timeout_seconds
                )
                
                # Validate confidence threshold
                if result.confidence >= self.llm_confidence_threshold:
                    return result
                else:
                    self.logger.warning(
                        f"LLM reasoning confidence {result.confidence} below threshold {self.llm_confidence_threshold}"
                    )
                    if attempt == self.max_llm_retries:
                        return result  # Return low-confidence result on final attempt
                    
            except asyncio.TimeoutError:
                last_exception = LLMTimeoutError(
                    f"LLM reasoning timed out after {self.llm_timeout_seconds} seconds",
                    timeout_seconds=self.llm_timeout_seconds
                )
                self.logger.warning(f"LLM reasoning attempt {attempt + 1} timed out")
                
            except (LLMAPIError, LLMRateLimitError) as e:
                last_exception = e
                self.logger.warning(f"LLM API error on attempt {attempt + 1}: {str(e)}")
                
                # For rate limiting, wait before retry
                if isinstance(e, LLMRateLimitError) and attempt < self.max_llm_retries:
                    retry_after = getattr(e, 'retry_after', 5)
                    await asyncio.sleep(min(retry_after, 10))  # Cap wait time
                
            except Exception as e:
                last_exception = e
                self.logger.error(f"Unexpected error in LLM reasoning attempt {attempt + 1}: {str(e)}")
                break  # Don't retry on unexpected errors
        
        # All attempts failed
        if last_exception:
            raise last_exception
        else:
            raise RuntimeError("LLM reasoning failed after all attempts")
    
    async def _try_causal_reasoning(self, context: ReasoningContext) -> ReasoningResult:
        """Attempt causal reasoning strategy."""
        return await self.causal_strategy.reason(context)
    
    async def _try_statistical_reasoning(self, context: ReasoningContext) -> ReasoningResult:
        """Attempt statistical reasoning strategy."""
        return await self.statistical_strategy.reason(context)
    
    def _is_valid_result(self, result: Optional[ReasoningResult], strategy_name: str) -> bool:
        """Validate if a reasoning result is acceptable."""
        
        if result is None:
            return False
        
        # Check basic structure
        if not hasattr(result, 'insights') or not hasattr(result, 'confidence'):
            return False
        
        # Check for empty results
        if not result.insights:
            return False
        
        # Strategy-specific validation
        if strategy_name == "agentic_llm":
            # LLM results should have reasonable confidence
            if result.confidence < 0.1:
                return False
            
            # Should have meaningful insights
            if len(result.insights) == 1 and "error" in str(result.insights[0]).lower():
                return False
        
        elif strategy_name in ["causal", "statistical"]:
            # Traditional strategies should have some confidence
            if result.confidence < 0.2:
                return False
        
        return True
    
    def _should_continue_fallback(self, error: Exception) -> bool:
        """Determine if fallback should continue based on error type."""
        
        # Continue fallback for these error types
        continue_on_errors = [
            LLMAPIError,
            LLMTimeoutError,
            LLMRateLimitError,
            ConnectionError,
            TimeoutError
        ]
        
        return any(isinstance(error, error_type) for error_type in continue_on_errors)
    
    def _update_confidence_tracking(self, strategy_name: str, confidence: float) -> None:
        """Update running average of confidence for strategy performance tracking."""
        
        perf = self.strategy_performance[strategy_name]
        current_avg = perf["avg_confidence"]
        successes = perf["successes"]
        
        # Update running average
        if successes == 1:
            perf["avg_confidence"] = confidence
        else:
            perf["avg_confidence"] = ((current_avg * (successes - 1)) + confidence) / successes
    
    def _enhance_result_with_metadata(
        self,
        result: ReasoningResult,
        strategy_used: str,
        attempts: List[Dict[str, Any]]
    ) -> ReasoningResult:
        """Enhance reasoning result with fallback metadata."""
        
        # Add fallback metadata to insights
        enhanced_insights = list(result.insights)
        
        fallback_metadata = {
            "type": "fallback_strategy_info",
            "strategy_used": strategy_used,
            "fallback_attempts": len(attempts),
            "failed_strategies": [attempt["strategy"] for attempt in attempts],
            "strategy_performance": dict(self.strategy_performance),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        enhanced_insights.append(fallback_metadata)
        
        # Create new result with enhanced insights
        return ReasoningResult(
            insights=enhanced_insights,
            confidence=result.confidence,
            recommendations=result.recommendations
        )
    
    def _create_emergency_fallback_result(
        self,
        context: ReasoningContext,
        attempts: List[Dict[str, Any]]
    ) -> ReasoningResult:
        """Create an emergency fallback result when all strategies fail."""
        
        self.logger.error("All reasoning strategies failed, creating emergency fallback result")
        
        insights = [
            {
                "type": "emergency_fallback",
                "message": "All reasoning strategies failed",
                "system_id": context.system_id,
                "failed_attempts": attempts,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]
        
        # Try to provide basic recommendations based on context
        recommendations = []
        
        # Basic heuristics based on current state
        current_state = context.current_state
        if current_state and "metrics" in current_state:
            metrics = current_state["metrics"]
            
            # Simple threshold-based recommendations
            for metric_name, metric_value in metrics.items():
                try:
                    value = float(getattr(metric_value, 'value', metric_value))
                    
                    if "cpu" in metric_name.lower() and value > 80:
                        recommendations.append({
                            "action_type": "scale_out",
                            "parameters": {"scale_factor": 1.5},
                            "source": "emergency_fallback",
                            "reason": f"High CPU usage: {value}%"
                        })
                    elif "memory" in metric_name.lower() and value > 85:
                        recommendations.append({
                            "action_type": "scale_out",
                            "parameters": {"scale_factor": 1.3},
                            "source": "emergency_fallback",
                            "reason": f"High memory usage: {value}%"
                        })
                    elif "latency" in metric_name.lower() and value > 1000:
                        recommendations.append({
                            "action_type": "scale_out",
                            "parameters": {"scale_factor": 2.0},
                            "source": "emergency_fallback",
                            "reason": f"High latency: {value}ms"
                        })
                        
                except (ValueError, TypeError, AttributeError):
                    continue
        
        return ReasoningResult(
            insights=insights,
            confidence=0.2,  # Low confidence for emergency fallback
            recommendations=recommendations
        )
    
    def get_strategy_performance(self) -> Dict[str, Any]:
        """Get performance statistics for all strategies."""
        
        performance_summary = {}
        
        for strategy_name, perf in self.strategy_performance.items():
            attempts = perf["attempts"]
            successes = perf["successes"]
            
            performance_summary[strategy_name] = {
                "attempts": attempts,
                "successes": successes,
                "success_rate": (successes / attempts) if attempts > 0 else 0.0,
                "average_confidence": perf["avg_confidence"],
                "reliability_score": self._calculate_reliability_score(perf)
            }
        
        return performance_summary
    
    def _calculate_reliability_score(self, perf: Dict[str, Any]) -> float:
        """Calculate a reliability score for a strategy based on performance."""
        
        attempts = perf["attempts"]
        successes = perf["successes"]
        avg_confidence = perf["avg_confidence"]
        
        if attempts == 0:
            return 0.0
        
        success_rate = successes / attempts
        
        # Combine success rate and average confidence
        reliability = (success_rate * 0.7) + (avg_confidence * 0.3)
        
        return min(1.0, reliability)
    
    def reset_performance_tracking(self) -> None:
        """Reset performance tracking statistics."""
        
        for strategy_name in self.strategy_performance:
            self.strategy_performance[strategy_name] = {
                "attempts": 0,
                "successes": 0,
                "avg_confidence": 0.0
            }
        
        self.logger.info("Reset strategy performance tracking")
    
    def configure_fallback_behavior(
        self,
        enable_llm_fallback: Optional[bool] = None,
        llm_confidence_threshold: Optional[float] = None,
        llm_timeout_seconds: Optional[float] = None,
        max_llm_retries: Optional[int] = None
    ) -> None:
        """Configure fallback behavior parameters."""
        
        if enable_llm_fallback is not None:
            self.enable_llm_fallback = enable_llm_fallback
        
        if llm_confidence_threshold is not None:
            self.llm_confidence_threshold = llm_confidence_threshold
            self.agentic_strategy.confidence_threshold = llm_confidence_threshold
        
        if llm_timeout_seconds is not None:
            self.llm_timeout_seconds = llm_timeout_seconds
        
        if max_llm_retries is not None:
            self.max_llm_retries = max_llm_retries
        
        self.logger.info("Updated fallback configuration")


def create_fallback_reasoning_strategy(
    llm_client: LLMClient,
    world_model: PolarisWorldModel,
    knowledge_base: PolarisKnowledgeBase,
    **kwargs
) -> FallbackReasoningStrategy:
    """
    Factory function to create a fallback reasoning strategy with sensible defaults.
    
    Args:
        llm_client: LLM client for agentic reasoning
        world_model: World model for predictions and simulations
        knowledge_base: Knowledge base for historical data
        **kwargs: Additional configuration parameters
        
    Returns:
        Configured FallbackReasoningStrategy instance
    """
    
    return FallbackReasoningStrategy(
        llm_client=llm_client,
        world_model=world_model,
        knowledge_base=knowledge_base,
        **kwargs
    )