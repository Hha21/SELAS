"""
LLM World Model Implementation

Implements an LLM-powered world model that extends PolarisWorldModel to provide
intelligent system behavior understanding and prediction using natural language
processing and reasoning capabilities.

Key Features:
- Natural language system state representation
- LLM-powered behavior prediction and forecasting
- Causal reasoning for adaptation impact simulation
- Conversation history management for context continuity
- Integration with existing POLARIS observability framework
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from ..domain.models import SystemState, MetricValue
from ..framework.events import TelemetryEvent
from ..infrastructure.llm import (
    LLMClient, ConversationManager, PromptManager, ResponseParser,
    Message, MessageRole, LLMRequest, AgenticConversation
)
from ..infrastructure.observability import (
    get_logger, get_metrics_collector, get_tracer, observe_polaris_component,
    trace_world_model_operation
)
from .world_model import PolarisWorldModel, PredictionResult, SimulationResult
from .knowledge_base import PolarisKnowledgeBase


class SystemStateNarrator:
    """Converts system metrics and state to natural language descriptions."""
    
    def __init__(self):
        self.logger = get_digital_twin_logger("system_state_narrator")
    
    def narrate_system_state(self, system_state: SystemState) -> str:
        """Convert system state to natural language description."""
        try:
            narrative_parts = [
                f"System '{system_state.system_id}' status at {system_state.timestamp.isoformat()}:",
                f"Overall health: {system_state.health_status.value}"
            ]
            
            if system_state.metrics:
                narrative_parts.append("Current metrics:")
                for metric_name, metric_value in system_state.metrics.items():
                    unit_str = f" {metric_value.unit}" if metric_value.unit else ""
                    narrative_parts.append(
                        f"  - {metric_name}: {metric_value.value}{unit_str}"
                    )
            
            if system_state.metadata:
                narrative_parts.append("Additional context:")
                for key, value in system_state.metadata.items():
                    narrative_parts.append(f"  - {key}: {value}")
            
            return "\n".join(narrative_parts)
            
        except Exception as e:
            self.logger.error(f"Error narrating system state: {str(e)}")
            return f"System '{system_state.system_id}' - Error generating narrative: {str(e)}"
    
    def narrate_metrics_trend(self, metrics_history: List[Dict[str, Any]]) -> str:
        """Generate narrative description of metrics trends."""
        if not metrics_history:
            return "No historical metrics available for trend analysis."
        
        try:
            narrative_parts = ["Recent metrics trends:"]
            
            # Group metrics by name
            metric_groups = {}
            for entry in metrics_history:
                for metric_name, metric_data in entry.get("metrics", {}).items():
                    if metric_name not in metric_groups:
                        metric_groups[metric_name] = []
                    metric_groups[metric_name].append(metric_data)
            
            # Analyze trends for each metric
            for metric_name, values in metric_groups.items():
                if len(values) >= 2:
                    first_val = values[0].get("value", 0)
                    last_val = values[-1].get("value", 0)
                    
                    try:
                        first_num = float(first_val)
                        last_num = float(last_val)
                        
                        if first_num != 0:
                            change_pct = ((last_num - first_num) / first_num) * 100
                            trend = "increasing" if change_pct > 5 else "decreasing" if change_pct < -5 else "stable"
                            narrative_parts.append(
                                f"  - {metric_name}: {trend} ({change_pct:+.1f}% change)"
                            )
                        else:
                            narrative_parts.append(f"  - {metric_name}: current value {last_num}")
                    except (ValueError, TypeError):
                        narrative_parts.append(f"  - {metric_name}: non-numeric values")
            
            return "\n".join(narrative_parts)
            
        except Exception as e:
            self.logger.error(f"Error narrating metrics trend: {str(e)}")
            return f"Error analyzing metrics trends: {str(e)}"


@observe_polaris_component("llm_world_model", auto_trace=True, auto_metrics=True)
class LLMWorldModel(PolarisWorldModel):
    """
    LLM-powered world model implementation.
    
    Extends PolarisWorldModel to provide intelligent system behavior understanding
    and prediction using Large Language Models. Features include:
    - Natural language system state representation
    - LLM-powered behavior prediction and forecasting  
    - Causal reasoning for adaptation impact simulation
    - Conversation history management for context continuity
    - Integration with existing POLARIS framework components
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        knowledge_base: Optional[PolarisKnowledgeBase] = None,
        conversation_history_limit: int = 10,
        fallback_model: Optional[PolarisWorldModel] = None
    ):
        """
        Initialize LLM World Model.
        
        Args:
            llm_client: LLM client for API interactions
            knowledge_base: Optional knowledge base for historical data
            conversation_history_limit: Maximum conversation history to maintain
            fallback_model: Optional fallback world model for error scenarios
        """
        self.llm_client = llm_client
        self.knowledge_base = knowledge_base
        self.conversation_history_limit = conversation_history_limit
        self.fallback_model = fallback_model
        
        # Initialize components
        self.narrator = SystemStateNarrator()
        self.response_parser = ResponseParser()
        
        # Conversation history for context continuity
        self.conversation_history: Dict[str, List[Message]] = {}
        
        # System state cache for context building
        self.system_states: Dict[str, List[SystemState]] = {}
        
        # Use POLARIS logging and observability
        self.logger = get_logger("polaris.llm_world_model")
        self.metrics = get_metrics_collector()
        self.tracer = get_tracer()
        
        # Register LLM world model specific metrics
        self._register_world_model_metrics()
        
        self.logger.info("LLM World Model initialized", extra={
            "conversation_history_limit": conversation_history_limit,
            "has_knowledge_base": knowledge_base is not None,
            "has_fallback_model": fallback_model is not None
        })
    
    def _register_world_model_metrics(self) -> None:
        """Register LLM world model specific metrics."""
        try:
            # World model prediction metrics
            self.metrics.register_counter(
                "polaris_llm_world_model_predictions_total",
                "Total world model predictions made",
                ["system_id", "prediction_type", "status"]
            )
            
            # World model simulation metrics
            self.metrics.register_counter(
                "polaris_llm_world_model_simulations_total",
                "Total adaptation impact simulations",
                ["system_id", "action_type", "status"]
            )
            
            # Prediction accuracy tracking
            self.metrics.register_histogram(
                "polaris_llm_world_model_prediction_confidence",
                "Confidence scores for world model predictions",
                labels=["system_id", "prediction_type"]
            )
            
            # LLM API performance for world model
            self.metrics.register_histogram(
                "polaris_llm_world_model_api_duration_seconds",
                "Duration of LLM API calls for world model operations",
                labels=["system_id", "operation_type"]
            )
            
            # System state updates
            self.metrics.register_counter(
                "polaris_llm_world_model_state_updates_total",
                "Total system state updates processed",
                ["system_id"]
            )
            
        except Exception as e:
            self.logger.warning("Failed to register world model metrics", extra={"error": str(e)})
    
    async def update_system_state(self, telemetry: TelemetryEvent) -> None:
        """
        Update the world model with new telemetry data.
        
        Maintains system state history and updates conversation context
        with natural language representation of the system state.
        """
        try:
            system_state = telemetry.system_state
            system_id = system_state.system_id
            
            # Store system state in history
            if system_id not in self.system_states:
                self.system_states[system_id] = []
            
            self.system_states[system_id].append(system_state)
            
            # Limit history size
            if len(self.system_states[system_id]) > 50:
                self.system_states[system_id] = self.system_states[system_id][-50:]
            
            # Generate natural language representation
            narrative = self.narrator.narrate_system_state(system_state)
            
            # Update conversation history with system state update
            if system_id not in self.conversation_history:
                self.conversation_history[system_id] = []
            
            state_message = Message(
                role=MessageRole.USER,
                content=f"System state update:\n{narrative}",
                metadata={
                    "type": "system_state_update",
                    "system_id": system_id,
                    "timestamp": system_state.timestamp.isoformat()
                }
            )
            
            self.conversation_history[system_id].append(state_message)
            
            # Limit conversation history
            if len(self.conversation_history[system_id]) > self.conversation_history_limit:
                self.conversation_history[system_id] = self.conversation_history[system_id][-self.conversation_history_limit:]
            
            self.logger.debug(f"Updated system state for {system_id}")
            
        except Exception as e:
            self.logger.error(f"Error updating system state: {str(e)}")
            # Don't raise exception to avoid breaking the telemetry pipeline
    
    def _build_system_context(self, system_id: str) -> str:
        """Build comprehensive system context for LLM prompts."""
        context_parts = []
        
        # Add system overview
        context_parts.append(f"System ID: {system_id}")
        
        # Add recent system states
        if system_id in self.system_states and self.system_states[system_id]:
            recent_states = self.system_states[system_id][-5:]  # Last 5 states
            context_parts.append("Recent system states:")
            for state in recent_states:
                narrative = self.narrator.narrate_system_state(state)
                context_parts.append(f"  {narrative}")
        
        # Add metrics trends if available
        if system_id in self.system_states and len(self.system_states[system_id]) > 1:
            metrics_history = []
            for state in self.system_states[system_id][-10:]:  # Last 10 for trend analysis
                metrics_data = {}
                for name, metric in state.metrics.items():
                    metrics_data[name] = {
                        "value": metric.value,
                        "unit": metric.unit,
                        "timestamp": metric.timestamp.isoformat() if metric.timestamp else None
                    }
                metrics_history.append({
                    "timestamp": state.timestamp.isoformat(),
                    "metrics": metrics_data
                })
            
            trend_narrative = self.narrator.narrate_metrics_trend(metrics_history)
            context_parts.append(trend_narrative)
        
        # Add knowledge base context if available
        if self.knowledge_base:
            try:
                # Get system information from knowledge base
                system_info = self.knowledge_base.get_system_info(system_id)
                if system_info:
                    context_parts.append(f"System information: {system_info}")
                
                # Get recent patterns
                recent_patterns = self.knowledge_base.get_recent_patterns(system_id, limit=3)
                if recent_patterns:
                    context_parts.append("Recent learned patterns:")
                    for pattern in recent_patterns:
                        context_parts.append(f"  - {pattern}")
                        
            except Exception as e:
                self.logger.warning(f"Error retrieving knowledge base context: {str(e)}")
        
        return "\n\n".join(context_parts)
    
    def _get_conversation_messages(self, system_id: str, additional_context: str = "") -> List[Message]:
        """Get conversation messages for LLM request."""
        messages = []
        
        # Add system message with context
        system_content = f"""You are an intelligent system behavior analyst and predictor for the POLARIS adaptation framework.

Your role is to analyze system behavior, predict future states, and simulate the impact of adaptation actions using your understanding of system dynamics, performance patterns, and causal relationships.

System Context:
{self._build_system_context(system_id)}

{additional_context}

Provide accurate, data-driven analysis with confidence estimates. Use structured JSON responses when requested."""
        
        messages.append(Message(
            role=MessageRole.SYSTEM,
            content=system_content
        ))
        
        # Add conversation history
        if system_id in self.conversation_history:
            messages.extend(self.conversation_history[system_id])
        
        return messages 
           
    @trace_world_model_operation("behavior_prediction")
    async def predict_system_behavior(self, system_id: str, time_horizon: int) -> PredictionResult:
        """
        Predict future system behavior using LLM forecasting.
        
        Uses LLM capabilities to analyze current trends, historical patterns,
        and system dynamics to forecast future behavior within the specified
        time horizon.
        
        Args:
            system_id: ID of the system to predict
            time_horizon: Prediction time horizon in minutes
            
        Returns:
            PredictionResult with predicted outcomes and confidence score
        """
        try:
            # Build prediction prompt
            prediction_prompt = f"""Analyze the system behavior and predict future state for the next {time_horizon} minutes.

            Based on the current system state, recent trends, and historical patterns, provide predictions for:
            1. Key performance metrics (CPU, memory, response time, throughput, etc.)
            2. System health status
            3. Potential issues or anomalies
            4. Resource utilization trends

            Respond with a JSON object containing:
            {{
                "predictions": {{
                    "metric_name": {{
                        "predicted_value": <number>,
                        "confidence": <0.0-1.0>,
                        "trend": "increasing|decreasing|stable",
                        "reasoning": "explanation"
                    }}
                }},
                "health_prediction": {{
                    "status": "healthy|warning|critical|unhealthy",
                    "confidence": <0.0-1.0>,
                    "reasoning": "explanation"
                }},
                "potential_issues": [
                    {{
                        "issue": "description",
                        "probability": <0.0-1.0>,
                        "impact": "low|medium|high",
                        "timeframe": "minutes until likely occurrence"
                    }}
                ],
                "overall_confidence": <0.0-1.0>,
                "prediction_horizon_minutes": {time_horizon}
            }}"""
            
            # Get conversation messages
            messages = self._get_conversation_messages(
                system_id, 
                f"Time horizon for prediction: {time_horizon} minutes"
            )
            
            # Add prediction request
            messages.append(Message(
                role=MessageRole.USER,
                content=prediction_prompt
            ))
            
            # Create LLM request
            request = LLMRequest(
                messages=messages,
                model_name=self.llm_client.config.model_name,
                max_tokens=1500,
                temperature=0.1  # Low temperature for consistent predictions
            )
            
            # Generate response
            response = await self.llm_client.generate_response(request)
            
            # Parse response
            try:
                prediction_data = json.loads(response.content)
                
                # Extract predictions into outcomes format
                outcomes = {}
                total_confidence = 0.0
                confidence_count = 0
                
                # Process metric predictions
                if "predictions" in prediction_data:
                    for metric_name, prediction in prediction_data["predictions"].items():
                        outcomes[f"{metric_name}_predicted"] = prediction.get("predicted_value")
                        outcomes[f"{metric_name}_trend"] = prediction.get("trend")
                        outcomes[f"{metric_name}_confidence"] = prediction.get("confidence", 0.5)
                        
                        if "confidence" in prediction:
                            total_confidence += prediction["confidence"]
                            confidence_count += 1
                
                # Process health prediction
                if "health_prediction" in prediction_data:
                    health_pred = prediction_data["health_prediction"]
                    outcomes["predicted_health_status"] = health_pred.get("status")
                    outcomes["health_confidence"] = health_pred.get("confidence", 0.5)
                    
                    if "confidence" in health_pred:
                        total_confidence += health_pred["confidence"]
                        confidence_count += 1
                
                # Process potential issues
                if "potential_issues" in prediction_data:
                    outcomes["potential_issues"] = prediction_data["potential_issues"]
                
                # Calculate overall confidence
                if confidence_count > 0:
                    avg_confidence = total_confidence / confidence_count
                else:
                    avg_confidence = prediction_data.get("overall_confidence", 0.5)
                
                # Store prediction in conversation history
                prediction_message = Message(
                    role=MessageRole.ASSISTANT,
                    content=response.content,
                    metadata={
                        "type": "behavior_prediction",
                        "time_horizon": time_horizon,
                        "confidence": avg_confidence
                    }
                )
                
                if system_id not in self.conversation_history:
                    self.conversation_history[system_id] = []
                self.conversation_history[system_id].append(prediction_message)
                
                self.logger.info(f"Generated behavior prediction for {system_id} with confidence {avg_confidence:.2f}")
                
                return PredictionResult(outcomes, avg_confidence)
                
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse LLM prediction response as JSON: {str(e)}")
                # Fallback to text-based prediction
                outcomes = {
                    "prediction_text": response.content,
                    "prediction_method": "text_analysis"
                }
                return PredictionResult(outcomes, 0.3)
                
        except Exception as e:
            self.logger.error(f"Error in LLM behavior prediction: {str(e)}")
            
            # Fallback to statistical model if available
            if self.fallback_model:
                try:
                    self.logger.info(f"Falling back to statistical model for {system_id}")
                    return await self.fallback_model.predict_system_behavior(system_id, time_horizon)
                except Exception as fallback_error:
                    self.logger.error(f"Fallback model also failed: {str(fallback_error)}")
            
            # Return minimal prediction result
            return PredictionResult(
                {"error": str(e), "prediction_method": "error_fallback"}, 
                0.0
            )
    
    async def simulate_adaptation_impact(self, system_id: str, action: Any) -> SimulationResult:
        """
        Simulate the impact of an adaptation action using LLM causal reasoning.
        
        Uses LLM capabilities to perform what-if scenario analysis and predict
        the outcomes of applying the specified adaptation action to the system.
        
        Args:
            system_id: ID of the target system
            action: Adaptation action to simulate (AdaptationAction or dict)
            
        Returns:
            SimulationResult with simulated outcomes and confidence score
        """
        try:
            # Convert action to dict if needed
            if hasattr(action, '__dict__'):
                action_dict = {
                    "action_type": getattr(action, 'action_type', 'unknown'),
                    "parameters": getattr(action, 'parameters', {}),
                    "target_system": getattr(action, 'target_system', system_id)
                }
            elif isinstance(action, dict):
                action_dict = action
            else:
                action_dict = {"action_type": str(action), "parameters": {}}
            
            # Build simulation prompt
            simulation_prompt = f"""Simulate the impact of the following adaptation action on the system:

            Action Details:
            - Type: {action_dict.get('action_type', 'unknown')}
            - Parameters: {json.dumps(action_dict.get('parameters', {}), indent=2)}
            - Target System: {action_dict.get('target_system', system_id)}

            Based on the current system state, historical patterns, and your understanding of system dynamics, predict:
            1. Immediate effects (0-5 minutes)
            2. Short-term effects (5-30 minutes)  
            3. Long-term effects (30+ minutes)
            4. Potential side effects or risks
            5. Success probability and confidence

            Consider:
            - Current system load and capacity
            - Historical response to similar actions
            - System dependencies and constraints
            - Resource availability and limits

            Respond with a JSON object containing:
            {{
                "immediate_effects": {{
                    "metric_changes": {{
                        "metric_name": {{
                            "current_value": <number>,
                            "predicted_value": <number>,
                            "change_percentage": <number>,
                            "confidence": <0.0-1.0>
                        }}
                    }},
                    "system_behavior": "description of immediate behavioral changes"
                }},
                "short_term_effects": {{
                    "metric_changes": {{}},
                    "system_behavior": "description"
                }},
                "long_term_effects": {{
                    "metric_changes": {{}},
                    "system_behavior": "description"
                }},
                "risks_and_side_effects": [
                    {{
                        "risk": "description",
                        "probability": <0.0-1.0>,
                        "severity": "low|medium|high",
                        "mitigation": "suggested mitigation"
                    }}
                ],
                "success_probability": <0.0-1.0>,
                "overall_confidence": <0.0-1.0>,
                "recommendation": "proceed|caution|abort",
                "reasoning": "detailed explanation of the simulation results"
            }}"""
            
            # Get conversation messages
            messages = self._get_conversation_messages(
                system_id,
                f"Simulating adaptation action: {action_dict}"
            )
            
            # Add simulation request
            messages.append(Message(
                role=MessageRole.USER,
                content=simulation_prompt
            ))
            
            # Create LLM request
            request = LLMRequest(
                messages=messages,
                model_name=self.llm_client.config.model_name,
                max_tokens=2000,
                temperature=0.1  # Low temperature for consistent simulations
            )
            
            # Generate response
            response = await self.llm_client.generate_response(request)
            
            # Parse response
            try:
                simulation_data = json.loads(response.content)
                
                # Extract simulation results into outcomes format
                outcomes = {}
                
                # Process immediate effects
                if "immediate_effects" in simulation_data:
                    immediate = simulation_data["immediate_effects"]
                    outcomes["immediate_effects"] = immediate
                    
                    if "metric_changes" in immediate:
                        for metric_name, change in immediate["metric_changes"].items():
                            outcomes[f"immediate_{metric_name}_change"] = change.get("change_percentage", 0)
                
                # Process short-term effects
                if "short_term_effects" in simulation_data:
                    outcomes["short_term_effects"] = simulation_data["short_term_effects"]
                
                # Process long-term effects
                if "long_term_effects" in simulation_data:
                    outcomes["long_term_effects"] = simulation_data["long_term_effects"]
                
                # Process risks
                if "risks_and_side_effects" in simulation_data:
                    outcomes["risks"] = simulation_data["risks_and_side_effects"]
                
                # Extract success probability and confidence
                success_prob = simulation_data.get("success_probability", 0.5)
                confidence = simulation_data.get("overall_confidence", 0.5)
                
                outcomes["success_probability"] = success_prob
                outcomes["recommendation"] = simulation_data.get("recommendation", "caution")
                outcomes["reasoning"] = simulation_data.get("reasoning", "")
                
                # Store simulation in conversation history
                simulation_message = Message(
                    role=MessageRole.ASSISTANT,
                    content=response.content,
                    metadata={
                        "type": "adaptation_simulation",
                        "action": action_dict,
                        "success_probability": success_prob,
                        "confidence": confidence
                    }
                )
                
                if system_id not in self.conversation_history:
                    self.conversation_history[system_id] = []
                self.conversation_history[system_id].append(simulation_message)
                
                self.logger.info(f"Generated adaptation simulation for {system_id} with confidence {confidence:.2f}")
                
                return SimulationResult(outcomes, confidence)
                
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse LLM simulation response as JSON: {str(e)}")
                # Fallback to text-based simulation
                outcomes = {
                    "simulation_text": response.content,
                    "simulation_method": "text_analysis"
                }
                return SimulationResult(outcomes, 0.3)
                
        except Exception as e:
            self.logger.error(f"Error in LLM adaptation simulation: {str(e)}")
            
            # Fallback to statistical model if available
            if self.fallback_model:
                try:
                    self.logger.info(f"Falling back to statistical model for simulation on {system_id}")
                    return await self.fallback_model.simulate_adaptation_impact(system_id, action)
                except Exception as fallback_error:
                    self.logger.error(f"Fallback model also failed: {str(fallback_error)}")
            
            # Return minimal simulation result
            return SimulationResult(
                {"error": str(e), "simulation_method": "error_fallback"}, 
                0.0
            )
    
    def get_conversation_history(self, system_id: str) -> List[Message]:
        """Get conversation history for a system."""
        return self.conversation_history.get(system_id, []).copy()
    
    def clear_conversation_history(self, system_id: Optional[str] = None) -> None:
        """Clear conversation history for a system or all systems."""
        if system_id:
            if system_id in self.conversation_history:
                del self.conversation_history[system_id]
                self.logger.info(f"Cleared conversation history for {system_id}")
        else:
            self.conversation_history.clear()
            self.logger.info("Cleared all conversation history")
    
    def get_system_states_history(self, system_id: str, limit: Optional[int] = None) -> List[SystemState]:
        """Get system states history for a system."""
        states = self.system_states.get(system_id, [])
        if limit:
            return states[-limit:]
        return states.copy()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the LLM world model."""
        total_conversations = sum(len(history) for history in self.conversation_history.values())
        total_systems = len(self.system_states)
        total_states = sum(len(states) for states in self.system_states.values())
        
        return {
            "total_systems_tracked": total_systems,
            "total_system_states": total_states,
            "total_conversation_messages": total_conversations,
            "systems_with_conversations": len(self.conversation_history),
            "llm_provider": self.llm_client.get_provider().value,
            "conversation_history_limit": self.conversation_history_limit,
            "has_fallback_model": self.fallback_model is not None,
            "has_knowledge_base": self.knowledge_base is not None
        }