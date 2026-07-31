"""
Agentic LLM Tools for POLARIS Reasoning Strategy

Implements specialized tools that allow the LLM agent to interact with
the POLARIS framework components dynamically during reasoning.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

from ..infrastructure.llm.tool_registry import BaseTool, ToolRegistry
from ..infrastructure.llm.models import ToolSchema
from ..infrastructure.llm.exceptions import LLMToolError
from ..digital_twin.world_model import PolarisWorldModel, PredictionResult, SimulationResult
from ..digital_twin.knowledge_base import PolarisKnowledgeBase
from ..domain.models import SystemState, AdaptationAction, HealthStatus


class WorldModelTool(BaseTool):
    """Tool for querying world model predictions and simulations."""
    
    def __init__(self, world_model: PolarisWorldModel):
        super().__init__(
            name="world_model_query",
            description="Query the world model for system behavior predictions and adaptation impact simulations"
        )
        self.world_model = world_model
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "operation": {
                    "type": "string",
                    "enum": ["predict_behavior", "simulate_action"],
                    "description": "Type of world model operation to perform"
                },
                "system_id": {
                    "type": "string",
                    "description": "Unique identifier of the target system"
                },
                "time_horizon": {
                    "type": "integer",
                    "description": "Time horizon in minutes for predictions (required for predict_behavior)",
                    "minimum": 1,
                    "maximum": 1440
                },
                "action": {
                    "type": "object",
                    "description": "Adaptation action to simulate (required for simulate_action)",
                    "properties": {
                        "action_type": {"type": "string"},
                        "parameters": {"type": "object"}
                    }
                }
            },
            required=["operation", "system_id"]
        )
    
    async def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        operation = parameters["operation"]
        system_id = parameters["system_id"]
        
        try:
            if operation == "predict_behavior":
                time_horizon = parameters.get("time_horizon", 60)  # Default 1 hour
                result = await self.world_model.predict_system_behavior(system_id, time_horizon)
                
                return {
                    "operation": "predict_behavior",
                    "system_id": system_id,
                    "time_horizon_minutes": time_horizon,
                    "predicted_outcomes": result.outcomes,
                    "confidence": result.probability,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
            elif operation == "simulate_action":
                action_data = parameters.get("action")
                if not action_data:
                    raise LLMToolError(
                        "Action data is required for simulate_action operation",
                        tool_name=self.name,
                        tool_parameters=parameters
                    )
                
                # Create AdaptationAction object for simulation
                action = AdaptationAction(
                    action_id="simulation",
                    action_type=action_data.get("action_type", "unknown"),
                    target_system=system_id,
                    parameters=action_data.get("parameters", {})
                )
                
                result = await self.world_model.simulate_adaptation_impact(system_id, action)
                
                return {
                    "operation": "simulate_action",
                    "system_id": system_id,
                    "simulated_action": {
                        "action_type": action.action_type,
                        "parameters": action.parameters
                    },
                    "predicted_outcomes": result.outcomes,
                    "confidence": result.probability,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            else:
                raise LLMToolError(
                    f"Unknown operation: {operation}",
                    tool_name=self.name,
                    tool_parameters=parameters
                )
                
        except Exception as e:
            if isinstance(e, LLMToolError):
                raise
            raise LLMToolError(
                f"World model operation failed: {str(e)}",
                tool_name=self.name,
                tool_parameters=parameters,
                cause=e
            )


class KnowledgeBaseTool(BaseTool):
    """Tool for retrieving historical data and pattern retrieval."""
    
    def __init__(self, knowledge_base: PolarisKnowledgeBase):
        super().__init__(
            name="knowledge_base_query",
            description="Query the knowledge base for historical patterns, system behavior, and adaptation history"
        )
        self.knowledge_base = knowledge_base
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "operation": {
                    "type": "string",
                    "enum": ["get_similar_patterns", "get_adaptation_history", "query_system_behavior"],
                    "description": "Type of knowledge base query to perform"
                },
                "system_id": {
                    "type": "string",
                    "description": "Unique identifier of the target system"
                },
                "conditions": {
                    "type": "object",
                    "description": "Conditions to match for pattern similarity (required for get_similar_patterns)"
                },
                "action_type": {
                    "type": "string",
                    "description": "Filter adaptation history by action type (optional for get_adaptation_history)"
                },
                "behavior_type": {
                    "type": "string",
                    "description": "Type of behavior to analyze (required for query_system_behavior)",
                    "enum": ["anomaly", "stability", "trend", "degradation", "improvement"]
                },
                "similarity_threshold": {
                    "type": "number",
                    "description": "Minimum similarity threshold for pattern matching (0.0 to 1.0)",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.6
                }
            },
            required=["operation", "system_id"]
        )
    
    async def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        operation = parameters["operation"]
        system_id = parameters["system_id"]
        
        try:
            if operation == "get_similar_patterns":
                conditions = parameters.get("conditions", {})
                similarity_threshold = parameters.get("similarity_threshold", 0.6)
                
                patterns = await self.knowledge_base.get_similar_patterns(
                    conditions, similarity_threshold
                )
                
                return {
                    "operation": "get_similar_patterns",
                    "system_id": system_id,
                    "conditions": conditions,
                    "similarity_threshold": similarity_threshold,
                    "patterns": [
                        {
                            "pattern_id": p.pattern_id,
                            "pattern_type": p.pattern_type,
                            "conditions": p.conditions,
                            "outcomes": p.outcomes,
                            "confidence": p.confidence,
                            "usage_count": p.usage_count,
                            "learned_at": p.learned_at.isoformat()
                        }
                        for p in patterns[:10]  # Limit to top 10 patterns
                    ],
                    "total_found": len(patterns),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
            elif operation == "get_adaptation_history":
                action_type = parameters.get("action_type")
                
                history = await self.knowledge_base.get_adaptation_history(
                    system_id, action_type
                )
                
                return {
                    "operation": "get_adaptation_history",
                    "system_id": system_id,
                    "action_type_filter": action_type,
                    "history": history[:20],  # Limit to most recent 20 entries
                    "total_entries": len(history),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
            elif operation == "query_system_behavior":
                behavior_type = parameters.get("behavior_type")
                if not behavior_type:
                    raise LLMToolError(
                        "behavior_type is required for query_system_behavior operation",
                        tool_name=self.name,
                        tool_parameters=parameters
                    )
                
                behavior_data = await self.knowledge_base.query_system_behavior(
                    system_id, behavior_type
                )
                
                return {
                    "operation": "query_system_behavior",
                    "system_id": system_id,
                    "behavior_type": behavior_type,
                    "behavior_analysis": behavior_data,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            else:
                raise LLMToolError(
                    f"Unknown operation: {operation}",
                    tool_name=self.name,
                    tool_parameters=parameters
                )
                
        except Exception as e:
            if isinstance(e, LLMToolError):
                raise
            raise LLMToolError(
                f"Knowledge base query failed: {str(e)}",
                tool_name=self.name,
                tool_parameters=parameters,
                cause=e
            )


class SystemStateTool(BaseTool):
    """Tool for accessing current system metrics and health status."""
    
    def __init__(self, knowledge_base: PolarisKnowledgeBase):
        super().__init__(
            name="system_state_query",
            description="Query current system state including metrics, health status, and recent changes"
        )
        self.knowledge_base = knowledge_base
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "operation": {
                    "type": "string",
                    "enum": ["get_current_state", "get_recent_states", "get_health_summary"],
                    "description": "Type of system state query to perform"
                },
                "system_id": {
                    "type": "string",
                    "description": "Unique identifier of the target system"
                },
                "time_window_minutes": {
                    "type": "integer",
                    "description": "Time window in minutes for recent states (default: 60)",
                    "minimum": 1,
                    "maximum": 1440,
                    "default": 60
                },
                "include_metrics": {
                    "type": "boolean",
                    "description": "Whether to include detailed metrics (default: true)",
                    "default": True
                }
            },
            required=["operation", "system_id"]
        )
    
    async def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        operation = parameters["operation"]
        system_id = parameters["system_id"]
        include_metrics = parameters.get("include_metrics", True)
        
        try:
            if operation == "get_current_state":
                current_state = await self.knowledge_base.get_current_state(system_id)
                
                if not current_state:
                    return {
                        "operation": "get_current_state",
                        "system_id": system_id,
                        "state_found": False,
                        "message": "No current state available for system",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                
                result = {
                    "operation": "get_current_state",
                    "system_id": system_id,
                    "state_found": True,
                    "health_status": current_state.health_status.value,
                    "state_timestamp": current_state.timestamp.isoformat(),
                    "metadata": current_state.metadata,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                if include_metrics:
                    result["metrics"] = {
                        name: {
                            "value": metric.value,
                            "unit": metric.unit,
                            "timestamp": metric.timestamp.isoformat() if metric.timestamp else None,
                            "tags": metric.tags
                        }
                        for name, metric in current_state.metrics.items()
                    }
                
                return result
                
            elif operation == "get_recent_states":
                time_window = parameters.get("time_window_minutes", 60)
                end_time = datetime.now(timezone.utc)
                start_time = end_time - timedelta(minutes=time_window)
                
                states = await self.knowledge_base.get_historical_states(
                    system_id, start_time, end_time
                )
                
                result = {
                    "operation": "get_recent_states",
                    "system_id": system_id,
                    "time_window_minutes": time_window,
                    "states_found": len(states),
                    "time_range": {
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat()
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                if states:
                    result["states"] = []
                    for state in states[-10:]:  # Limit to most recent 10 states
                        state_data = {
                            "timestamp": state.timestamp.isoformat(),
                            "health_status": state.health_status.value,
                            "metadata": state.metadata
                        }
                        
                        if include_metrics:
                            state_data["metrics"] = {
                                name: {
                                    "value": metric.value,
                                    "unit": metric.unit
                                }
                                for name, metric in state.metrics.items()
                            }
                        
                        result["states"].append(state_data)
                
                return result
                
            elif operation == "get_health_summary":
                time_window = parameters.get("time_window_minutes", 60)
                end_time = datetime.now(timezone.utc)
                start_time = end_time - timedelta(minutes=time_window)
                
                states = await self.knowledge_base.get_historical_states(
                    system_id, start_time, end_time
                )
                
                # Analyze health status distribution
                health_counts = {}
                metric_trends = {}
                
                for state in states:
                    health_status = state.health_status.value
                    health_counts[health_status] = health_counts.get(health_status, 0) + 1
                    
                    # Track metric trends if metrics are included
                    if include_metrics:
                        for name, metric in state.metrics.items():
                            if name not in metric_trends:
                                metric_trends[name] = []
                            try:
                                value = float(metric.value)
                                metric_trends[name].append({
                                    "timestamp": state.timestamp.isoformat(),
                                    "value": value
                                })
                            except (ValueError, TypeError):
                                continue
                
                # Calculate trend summaries
                trend_summaries = {}
                for metric_name, values in metric_trends.items():
                    if len(values) >= 2:
                        first_val = values[0]["value"]
                        last_val = values[-1]["value"]
                        trend_summaries[metric_name] = {
                            "start_value": first_val,
                            "end_value": last_val,
                            "change": last_val - first_val,
                            "change_percent": ((last_val - first_val) / first_val * 100) if first_val != 0 else 0,
                            "data_points": len(values)
                        }
                
                return {
                    "operation": "get_health_summary",
                    "system_id": system_id,
                    "time_window_minutes": time_window,
                    "analysis_period": {
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat()
                    },
                    "health_distribution": health_counts,
                    "total_states": len(states),
                    "metric_trends": trend_summaries if include_metrics else {},
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            else:
                raise LLMToolError(
                    f"Unknown operation: {operation}",
                    tool_name=self.name,
                    tool_parameters=parameters
                )
                
        except Exception as e:
            if isinstance(e, LLMToolError):
                raise
            raise LLMToolError(
                f"System state query failed: {str(e)}",
                tool_name=self.name,
                tool_parameters=parameters,
                cause=e
            )


class ActionValidationTool(BaseTool):
    """Tool for checking action feasibility and validation."""
    
    def __init__(self, knowledge_base: PolarisKnowledgeBase):
        super().__init__(
            name="action_validation",
            description="Validate adaptation actions for feasibility, safety, and historical effectiveness"
        )
        self.knowledge_base = knowledge_base
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "operation": {
                    "type": "string",
                    "enum": ["validate_action", "check_action_history", "assess_action_risk"],
                    "description": "Type of action validation to perform"
                },
                "system_id": {
                    "type": "string",
                    "description": "Unique identifier of the target system"
                },
                "action": {
                    "type": "object",
                    "description": "Adaptation action to validate",
                    "properties": {
                        "action_type": {"type": "string"},
                        "parameters": {"type": "object"}
                    },
                    "required": ["action_type", "parameters"]
                },
                "risk_tolerance": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Risk tolerance level for action assessment (default: medium)",
                    "default": "medium"
                }
            },
            required=["operation", "system_id", "action"]
        )
    
    async def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        operation = parameters["operation"]
        system_id = parameters["system_id"]
        action_data = parameters["action"]
        risk_tolerance = parameters.get("risk_tolerance", "medium")
        
        action_type = action_data["action_type"]
        action_params = action_data["parameters"]
        
        try:
            if operation == "validate_action":
                # Basic action validation
                validation_results = {
                    "is_valid": True,
                    "validation_errors": [],
                    "validation_warnings": []
                }
                
                # Check for required parameters based on action type
                if action_type == "scale_out":
                    if "scale_factor" not in action_params:
                        validation_results["validation_errors"].append("scale_factor parameter is required for scale_out action")
                        validation_results["is_valid"] = False
                    elif not isinstance(action_params["scale_factor"], (int, float)) or action_params["scale_factor"] <= 0:
                        validation_results["validation_errors"].append("scale_factor must be a positive number")
                        validation_results["is_valid"] = False
                    elif action_params["scale_factor"] > 10:
                        validation_results["validation_warnings"].append("scale_factor > 10 may cause resource exhaustion")
                
                elif action_type == "scale_in":
                    if "scale_factor" not in action_params:
                        validation_results["validation_errors"].append("scale_factor parameter is required for scale_in action")
                        validation_results["is_valid"] = False
                    elif not isinstance(action_params["scale_factor"], (int, float)) or action_params["scale_factor"] <= 0:
                        validation_results["validation_errors"].append("scale_factor must be a positive number")
                        validation_results["is_valid"] = False
                    elif action_params["scale_factor"] > 0.9:
                        validation_results["validation_warnings"].append("scale_factor > 0.9 may cause severe performance degradation")
                
                elif action_type == "restart":
                    if "graceful" not in action_params:
                        validation_results["validation_warnings"].append("graceful parameter not specified, assuming graceful restart")
                
                # Check current system state for context
                current_state = await self.knowledge_base.get_current_state(system_id)
                if current_state:
                    if current_state.health_status == HealthStatus.CRITICAL:
                        if action_type in ["scale_in", "restart"]:
                            validation_results["validation_warnings"].append(f"{action_type} action on CRITICAL system may worsen situation")
                
                return {
                    "operation": "validate_action",
                    "system_id": system_id,
                    "action": action_data,
                    "validation_result": validation_results,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
            elif operation == "check_action_history":
                # Check historical effectiveness of similar actions
                history = await self.knowledge_base.get_adaptation_history(system_id, action_type)
                
                # Analyze success rate and outcomes
                total_actions = len(history)
                successful_actions = 0
                failed_actions = 0
                
                for entry in history:
                    exec_result = entry.get("execution_result")
                    if exec_result:
                        if exec_result["status"] == "success":
                            successful_actions += 1
                        elif exec_result["status"] in ["failed", "timeout"]:
                            failed_actions += 1
                
                success_rate = (successful_actions / total_actions) if total_actions > 0 else 0
                
                return {
                    "operation": "check_action_history",
                    "system_id": system_id,
                    "action_type": action_type,
                    "historical_analysis": {
                        "total_executions": total_actions,
                        "successful_executions": successful_actions,
                        "failed_executions": failed_actions,
                        "success_rate": success_rate,
                        "recent_executions": history[:5]  # Most recent 5
                    },
                    "recommendation": (
                        "proceed" if success_rate >= 0.7 else
                        "caution" if success_rate >= 0.4 else
                        "avoid"
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
            elif operation == "assess_action_risk":
                # Assess risk based on action type, parameters, and system state
                risk_factors = []
                risk_score = 0.0  # 0.0 = low risk, 1.0 = high risk
                
                # Risk assessment based on action type
                if action_type == "restart":
                    risk_score += 0.6
                    risk_factors.append("restart actions cause temporary service interruption")
                elif action_type == "scale_in":
                    scale_factor = action_params.get("scale_factor", 1.0)
                    if scale_factor > 0.5:
                        risk_score += 0.4
                        risk_factors.append("significant scale-in may impact performance")
                elif action_type == "scale_out":
                    scale_factor = action_params.get("scale_factor", 1.0)
                    if scale_factor > 5:
                        risk_score += 0.3
                        risk_factors.append("large scale-out may exhaust resources")
                
                # Check current system health
                current_state = await self.knowledge_base.get_current_state(system_id)
                if current_state:
                    if current_state.health_status == HealthStatus.CRITICAL:
                        risk_score += 0.3
                        risk_factors.append("system is in critical state")
                    elif current_state.health_status == HealthStatus.WARNING:
                        risk_score += 0.1
                        risk_factors.append("system is in warning state")
                
                # Adjust risk based on tolerance
                risk_thresholds = {
                    "low": 0.2,
                    "medium": 0.5,
                    "high": 0.8
                }
                
                threshold = risk_thresholds[risk_tolerance]
                risk_level = (
                    "low" if risk_score <= threshold * 0.5 else
                    "medium" if risk_score <= threshold else
                    "high"
                )
                
                recommendation = (
                    "proceed" if risk_level == "low" else
                    "proceed_with_caution" if risk_level == "medium" else
                    "avoid_or_defer"
                )
                
                return {
                    "operation": "assess_action_risk",
                    "system_id": system_id,
                    "action": action_data,
                    "risk_assessment": {
                        "risk_score": min(1.0, risk_score),
                        "risk_level": risk_level,
                        "risk_factors": risk_factors,
                        "risk_tolerance": risk_tolerance,
                        "recommendation": recommendation
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            else:
                raise LLMToolError(
                    f"Unknown operation: {operation}",
                    tool_name=self.name,
                    tool_parameters=parameters
                )
                
        except Exception as e:
            if isinstance(e, LLMToolError):
                raise
            raise LLMToolError(
                f"Action validation failed: {str(e)}",
                tool_name=self.name,
                tool_parameters=parameters,
                cause=e
            )

def create_agentic_tool_registry(
    world_model: PolarisWorldModel,
    knowledge_base: PolarisKnowledgeBase
) -> ToolRegistry:
    """Create a tool registry with all agentic reasoning tools."""
    from ..infrastructure.llm.tool_registry import ToolRegistry
    
    registry = ToolRegistry()
    
    # Register all agentic tools
    registry.register_tool(WorldModelTool(world_model))
    registry.register_tool(KnowledgeBaseTool(knowledge_base))
    registry.register_tool(SystemStateTool(knowledge_base))
    registry.register_tool(ActionValidationTool(knowledge_base))
    
    return registry