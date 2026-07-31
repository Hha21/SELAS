"""
Control and Reasoning Module

Exports the main components for agentic LLM reasoning integration.
"""

from .reasoning_engine import (
    ReasoningStrategy,
    ReasoningContext,
    ReasoningResult,
    StatisticalReasoningStrategy,
    CausalReasoningStrategy,
    PolarisReasoningEngine
)

from .agentic_tools import (
    WorldModelTool,
    KnowledgeBaseTool,
    SystemStateTool,
    ActionValidationTool,
    create_agentic_tool_registry
)

from .agentic_llm_reasoning_strategy import AgenticLLMReasoningStrategy

from .agentic_execution_engine import (
    AgenticExecutionEngine,
    ExecutionContext,
    ReasoningTrace
)

from .fallback_reasoning_strategy import (
    FallbackReasoningStrategy,
    create_fallback_reasoning_strategy
)

from .adaptive_controller import (
    ControlStrategy,
    ReactiveControlStrategy,
    PredictiveControlStrategy,
    LearningControlStrategy,
    PolarisAdaptiveController,
    AdaptationNeed
)

from .pid_reactive_strategy import (
    PIDReactiveStrategy,
    PIDReactiveConfig
)

from .threshold_reactive_strategy import (
    ThresholdReactiveStrategy,
    ThresholdReactiveConfig,
    ThresholdRule,
    ThresholdCondition,
    ThresholdOperator,
    LogicalOperator
)

__all__ = [
    # Base reasoning components
    "ReasoningStrategy",
    "ReasoningContext", 
    "ReasoningResult",
    "StatisticalReasoningStrategy",
    "CausalReasoningStrategy",
    "PolarisReasoningEngine",
    
    # Agentic tools
    "WorldModelTool",
    "KnowledgeBaseTool", 
    "SystemStateTool",
    "ActionValidationTool",
    "create_agentic_tool_registry",
    
    # Agentic reasoning strategy
    "AgenticLLMReasoningStrategy",
    
    # Execution engine
    "AgenticExecutionEngine",
    "ExecutionContext",
    "ReasoningTrace",
    
    # Fallback strategy
    "FallbackReasoningStrategy",
    "create_fallback_reasoning_strategy",
    
    # Control strategies
    "ControlStrategy",
    "ReactiveControlStrategy", 
    "PredictiveControlStrategy",
    "LearningControlStrategy",
    "PolarisAdaptiveController",
    "AdaptationNeed",
    
    # PID reactive strategy
    "PIDReactiveStrategy",
    "PIDReactiveConfig",
    
    # Threshold reactive strategy
    "ThresholdReactiveStrategy",
    "ThresholdReactiveConfig",
    "ThresholdRule",
    "ThresholdCondition", 
    "ThresholdOperator",
    "LogicalOperator"
]