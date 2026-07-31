"""
Adaptive Controller Implementation

Provides the base classes and interfaces for adaptive control strategies.
This is a simplified implementation for the SWIM system demo.
"""

import logging
import time
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod

from ..domain.models import AdaptationAction
from ..framework.events import TelemetryEvent
from ..infrastructure.observability import get_logger


@dataclass
class AdaptationNeed:
    """Represents an identified need for system adaptation."""
    system_id: str
    is_needed: bool
    reason: str
    urgency: float = 0.5  # 0.0 to 1.0
    context: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.context is None:
            self.context = {}


class ControlStrategy(ABC):
    """Base class for control strategies."""
    
    @abstractmethod
    async def generate_actions(
        self, 
        system_id: str, 
        current_state: Dict[str, Any],
        adaptation_need: AdaptationNeed
    ) -> List[AdaptationAction]:
        """Generate adaptation actions based on current state and needs."""
        pass


class ReactiveControlStrategy(ControlStrategy):
    """Base class for reactive control strategies."""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
    
    async def generate_actions(
        self, 
        system_id: str, 
        current_state: Dict[str, Any],
        adaptation_need: AdaptationNeed
    ) -> List[AdaptationAction]:
        """Generate reactive adaptation actions."""
        # Simple fallback implementation
        actions = []
        
        if not adaptation_need.is_needed:
            return actions
        
        # Basic reactive logic based on urgency
        if adaptation_need.urgency > 0.8:
            # High urgency - scale up
            actions.append(AdaptationAction(
                action_id=f"reactive_{system_id}_{int(time.time())}",
                action_type="ADD_SERVER",
                target_system=system_id,
                parameters={"reason": "high_urgency_reactive"},
                priority=3
            ))
        elif adaptation_need.urgency < 0.3:
            # Low urgency - might scale down
            actions.append(AdaptationAction(
                action_id=f"reactive_{system_id}_{int(time.time())}",
                action_type="REMOVE_SERVER", 
                target_system=system_id,
                parameters={"reason": "low_urgency_reactive"},
                priority=1
            ))
        
        return actions


class PredictiveControlStrategy(ControlStrategy):
    """Base class for predictive control strategies."""
    
    def __init__(self, world_model=None):
        self.world_model = world_model
        self.logger = get_logger(self.__class__.__name__)
    
    async def generate_actions(
        self, 
        system_id: str, 
        current_state: Dict[str, Any],
        adaptation_need: AdaptationNeed
    ) -> List[AdaptationAction]:
        """Generate predictive adaptation actions."""
        # Placeholder implementation
        return []


class LearningControlStrategy(ControlStrategy):
    """Base class for learning-based control strategies."""
    
    def __init__(self, knowledge_base=None):
        self.knowledge_base = knowledge_base
        self.logger = get_logger(self.__class__.__name__)
    
    async def generate_actions(
        self, 
        system_id: str, 
        current_state: Dict[str, Any],
        adaptation_need: AdaptationNeed
    ) -> List[AdaptationAction]:
        """Generate learning-based adaptation actions."""
        # Placeholder implementation
        return []


class PolarisAdaptiveController:
    """
    Main adaptive controller that coordinates multiple control strategies.
    """
    
    def __init__(
        self,
        control_strategies: Optional[List[ControlStrategy]] = None,
        world_model=None,
        knowledge_base=None,
        event_bus=None,
        enable_pid_strategy: bool = False,
        pid_config: Optional[Dict[str, Any]] = None,
        enable_enhanced_assessment: bool = True,
    ):
        self.control_strategies = control_strategies or []
        self.world_model = world_model
        self.knowledge_base = knowledge_base
        self.event_bus = event_bus
        self.logger = get_logger(self.__class__.__name__)
        
        # Initialize enhanced assessment if enabled
        self.enable_enhanced_assessment = enable_enhanced_assessment
        if enable_enhanced_assessment:
            try:
                from .enhanced_adaptation_assessment import EnhancedAdaptationAssessment
                self.enhanced_assessor = EnhancedAdaptationAssessment(
                    world_model=world_model,
                    knowledge_base=knowledge_base
                )
                self.logger.info("Enhanced adaptation assessment enabled")
            except Exception as e:
                self.logger.warning(f"Could not initialize enhanced assessment: {e}")
                self.enhanced_assessor = None
                self.enable_enhanced_assessment = False
        else:
            self.enhanced_assessor = None
        
        # Add default strategies if none provided
        if not self.control_strategies:
            self.control_strategies.append(ReactiveControlStrategy())
    
    async def process_telemetry(self, telemetry: TelemetryEvent) -> None:
        """Process telemetry and trigger adaptation if needed."""
        try:
            system_id = telemetry.system_state.system_id
            
            # Assess adaptation need
            adaptation_need = await self.assess_adaptation_need(telemetry)
            
            if adaptation_need.is_needed:
                await self.trigger_adaptation_process(adaptation_need, telemetry)
                
        except Exception as e:
            self.logger.error(f"Error processing telemetry: {e}", exc_info=True)
    
    async def assess_adaptation_need(self, telemetry: TelemetryEvent) -> AdaptationNeed:
        """Assess whether adaptation is needed based on telemetry."""
        
        # Use enhanced assessment if available
        if self.enable_enhanced_assessment and self.enhanced_assessor:
            try:
                enhanced_need = await self.enhanced_assessor.assess_adaptation_need(telemetry)
                
                # Log enhanced assessment details
                if enhanced_need.is_needed:
                    trend_info = [f"{t.metric_name}:{t.direction.value}" for t in enhanced_need.trends[:3]]
                    self.logger.info(
                        f"🔍 ENHANCED ASSESSMENT [{enhanced_need.system_id}]: "
                        f"{enhanced_need.severity.value} - {enhanced_need.reason} "
                        f"(trends: {', '.join(trend_info)})",
                        extra={
                            "assessment_type": "enhanced",
                            "severity": enhanced_need.severity.value,
                            "confidence": enhanced_need.confidence,
                            "time_to_critical": enhanced_need.time_to_critical
                        }
                    )
                
                return enhanced_need
                
            except Exception as e:
                self.logger.warning(f"Enhanced assessment failed, falling back to basic: {e}")
        
        # Fallback to basic assessment
        system_state = telemetry.system_state
        system_id = system_state.system_id
        
        # Simple assessment based on health status
        is_needed = False
        reason = "No adaptation needed"
        urgency = 0.0
        
        if system_state.health_status.value in ["warning", "critical", "unhealthy"]:
            is_needed = True
            reason = f"System health is {system_state.health_status.value}"
            urgency = 0.7 if system_state.health_status.value == "warning" else 0.9
        
        # Check metrics for additional indicators
        metrics = system_state.metrics
        if metrics:
            # Check server utilization
            if "server_utilization" in metrics:
                util = metrics["server_utilization"].value
                if util > 0.8:
                    is_needed = True
                    reason = f"High server utilization: {util:.2f}"
                    urgency = max(urgency, 0.8)
                elif util < 0.2:
                    is_needed = True
                    reason = f"Low server utilization: {util:.2f}"
                    urgency = max(urgency, 0.3)
            
            # Check response time
            if "basic_response_time" in metrics:
                rt = metrics["basic_response_time"].value
                if rt > 1000:  # milliseconds
                    is_needed = True
                    reason = f"High response time: {rt}ms"
                    urgency = max(urgency, 0.7)
        
        return AdaptationNeed(
            system_id=system_id,
            is_needed=is_needed,
            reason=reason,
            urgency=urgency,
            context={"telemetry": telemetry}
        )
    
    async def trigger_adaptation_process(self, adaptation_need: AdaptationNeed, telemetry: TelemetryEvent = None) -> None:
        """Trigger the adaptation process."""
        try:
            system_id = adaptation_need.system_id
            
            # Get current state
            current_state = self._get_current_state_snapshot(system_id, telemetry)
            
            # Generate actions from all strategies
            all_actions = []
            for strategy in self.control_strategies:
                try:
                    actions = await strategy.generate_actions(system_id, current_state, adaptation_need)
                    all_actions.extend(actions)
                except Exception as e:
                    self.logger.error(f"Error in strategy {strategy.__class__.__name__}: {e}")
            
            # Publish adaptation event if we have actions
            if all_actions and self.event_bus:
                from ..framework.events import AdaptationEvent
                event = AdaptationEvent(
                    system_id=system_id,
                    reason=adaptation_need.reason,
                    suggested_actions=all_actions,
                    severity="high" if adaptation_need.urgency > 0.7 else "medium"
                )
                await self.event_bus.publish(event)
                
                self.logger.info(f"🔄 ADAPTATION TRIGGERED for {system_id}: {adaptation_need.reason} - {len(all_actions)} actions")
            
        except Exception as e:
            self.logger.error(f"Error triggering adaptation: {e}", exc_info=True)
    
    def _get_current_state_snapshot(self, system_id: str, telemetry: TelemetryEvent = None) -> Dict[str, Any]:
        """Get current state snapshot for a system."""
        if telemetry:
            # Use telemetry data as current state
            return {
                "metrics": telemetry.system_state.metrics,
                "health_status": telemetry.system_state.health_status,
                "timestamp": telemetry.system_state.timestamp,
                "system_id": system_id
            }
        # This would normally query the world model or data store
        # For now, return empty dict
        return {}
    
    async def start(self) -> None:
        """Start the adaptive controller."""
        self.logger.info("Adaptive controller started")
    
    async def stop(self) -> None:
        """Stop the adaptive controller."""
        self.logger.info("Adaptive controller stopped")