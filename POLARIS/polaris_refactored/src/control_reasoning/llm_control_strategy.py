"""
LLM-based Control Strategy

Implements a control strategy that uses LLM reasoning to generate adaptation actions.
This bridges the gap between the reasoning engine and the adaptive controller.
"""

import time
from typing import List, Dict, Any, Optional

from ..domain.models import AdaptationAction
from ..infrastructure.observability import get_logger, get_metrics_collector, trace_adaptation_flow
from .adaptive_controller import ControlStrategy, AdaptationNeed
from .reasoning_engine import PolarisReasoningEngine, ReasoningContext


class LLMControlStrategy(ControlStrategy):
    """
    LLM-based control strategy that uses the reasoning engine to generate actions.
    
    This strategy leverages the agentic LLM reasoning capabilities to analyze
    system state and generate intelligent adaptation actions.
    """
    
    def __init__(self, reasoning_engine: Optional[PolarisReasoningEngine] = None):
        self.reasoning_engine = reasoning_engine
        self.logger = get_logger(self.__class__.__name__)
        self.metrics = get_metrics_collector()
        
        self.logger.info("Initialized LLM Control Strategy")
    
    @trace_adaptation_flow("llm_control_strategy_generate_actions")
    async def generate_actions(
        self, 
        system_id: str, 
        current_state: Dict[str, Any],
        adaptation_need: AdaptationNeed
    ) -> List[AdaptationAction]:
        """Generate adaptation actions using LLM reasoning."""
        start_time = time.time()
        actions = []
        
        try:
            if not self.reasoning_engine:
                self.logger.warning("No reasoning engine available, falling back to simple actions")
                return self._generate_fallback_actions(system_id, current_state, adaptation_need)
            
            # Create reasoning context
            reasoning_context = ReasoningContext(
                system_id=system_id,
                current_state=current_state,
                adaptation_need=adaptation_need,
                context_data={
                    "metrics": current_state.get("metrics", {}),
                    "health_status": current_state.get("health_status"),
                    "urgency": adaptation_need.urgency,
                    "reason": adaptation_need.reason
                }
            )
            
            # Use reasoning engine to analyze and recommend actions
            reasoning_result = await self.reasoning_engine.reason(reasoning_context)
            
            if reasoning_result and hasattr(reasoning_result, 'recommended_actions') and reasoning_result.recommended_actions:
                actions = reasoning_result.recommended_actions
                
                self.logger.info(
                    f"LLM reasoning generated {len(actions)} actions for {system_id}",
                    extra={
                        "system_id": system_id,
                        "actions_count": len(actions),
                        "confidence": reasoning_result.confidence,
                        "reasoning_insights": len(reasoning_result.insights)
                    }
                )
            else:
                self.logger.info(f"LLM reasoning did not generate actions for {system_id}, using fallback")
                actions = self._generate_fallback_actions(system_id, current_state, adaptation_need)
            
            # Update metrics
            duration = time.time() - start_time
            self.metrics.record_histogram(
                "llm_control_strategy_duration", 
                duration, 
                {"system_id": system_id}
            )
            
        except Exception as e:
            self.logger.error(f"Error in LLM control strategy: {e}", exc_info=True)
            actions = self._generate_fallback_actions(system_id, current_state, adaptation_need)
        
        return actions
    
    def _generate_fallback_actions(
        self, 
        system_id: str, 
        current_state: Dict[str, Any],
        adaptation_need: AdaptationNeed
    ) -> List[AdaptationAction]:
        """Generate simple fallback actions when LLM reasoning fails."""
        actions = []
        
        if not adaptation_need.is_needed:
            return actions
        
        # Simple fallback logic based on urgency and metrics
        metrics = current_state.get("metrics", {})
        
        # Check server utilization for scaling decisions
        if "server_utilization" in metrics:
            utilization = metrics["server_utilization"].value
            server_count = metrics.get("server_count", {}).value if "server_count" in metrics else 1
            
            if utilization > 0.8 and server_count < 10:
                actions.append(AdaptationAction(
                    action_id=f"llm_fallback_{system_id}_{int(time.time())}",
                    action_type="ADD_SERVER",
                    target_system=system_id,
                    parameters={
                        "reason": "high_utilization_fallback",
                        "utilization": utilization,
                        "source": "llm_control_fallback"
                    },
                    priority=2
                ))
            elif utilization < 0.3 and server_count > 1:
                actions.append(AdaptationAction(
                    action_id=f"llm_fallback_{system_id}_{int(time.time())}",
                    action_type="REMOVE_SERVER",
                    target_system=system_id,
                    parameters={
                        "reason": "low_utilization_fallback",
                        "utilization": utilization,
                        "source": "llm_control_fallback"
                    },
                    priority=1
                ))
        
        # Check response time for QoS adjustments
        if "basic_response_time" in metrics:
            response_time = metrics["basic_response_time"].value
            if response_time > 1000:  # milliseconds
                actions.append(AdaptationAction(
                    action_id=f"llm_fallback_{system_id}_{int(time.time())}",
                    action_type="SET_DIMMER",
                    target_system=system_id,
                    parameters={
                        "value": 0.7,
                        "reason": "high_response_time_fallback",
                        "response_time": response_time,
                        "source": "llm_control_fallback"
                    },
                    priority=2
                ))
        
        if actions:
            self.logger.info(f"Generated {len(actions)} fallback actions for {system_id}")
        
        return actions