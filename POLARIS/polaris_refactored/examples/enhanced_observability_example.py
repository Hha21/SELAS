"""
Enhanced Observability Integration Example

This example demonstrates the enhanced observability features for concrete
adaptation components including PID controllers, LLM reasoning strategies,
and LLM world models with comprehensive tracing and metrics.
"""

import asyncio
from datetime import datetime
from typing import Dict, Any

from src.infrastructure.observability import (
    ObservabilityConfig, initialize_observability, shutdown_observability,
    get_logger, get_metrics_collector, get_tracer
)
from src.infrastructure.observability.config_examples import create_development_config
from src.control_reasoning.pid_reactive_strategy import PIDReactiveStrategy, PIDReactiveConfig
from src.control_reasoning.pid_controller import PIDConfig
from src.control_reasoning.agentic_llm_reasoning_strategy import AgenticLLMReasoningStrategy
from src.control_reasoning.reasoning_engine import ReasoningContext
from src.digital_twin.llm_world_model import LLMWorldModel
from src.infrastructure.llm.client import OpenAIClient
from src.infrastructure.llm.models import LLMConfiguration, LLMProvider
from src.domain.models import SystemState, MetricValue, HealthStatus, AdaptationNeed
from src.framework.events import TelemetryEvent


async def demonstrate_pid_observability():
    """Demonstrate PID controller observability features."""
    print("\n=== PID Controller Observability Demo ===")
    
    logger = get_logger("example.pid_demo")
    metrics = get_metrics_collector()
    tracer = get_tracer()
    
    # Create PID configuration
    pid_config = PIDReactiveConfig(
        controllers=[
            PIDConfig(
                metric_name="cpu_usage",
                setpoint=70.0,
                kp=1.0,
                ki=0.1,
                kd=0.05,
                min_output=-10.0,
                max_output=10.0
            ),
            PIDConfig(
                metric_name="memory_usage",
                setpoint=80.0,
                kp=0.8,
                ki=0.05,
                kd=0.02,
                min_output=-5.0,
                max_output=5.0
            )
        ]
    )
    
    # Create PID strategy (automatically instrumented)
    pid_strategy = PIDReactiveStrategy(pid_config)
    
    # Simulate system state with high CPU usage
    current_state = {
        "metrics": {
            "cpu_usage": MetricValue("cpu_usage", 85.0, "percent"),
            "memory_usage": MetricValue("memory_usage", 75.0, "percent"),
            "response_time": MetricValue("response_time", 150.0, "ms")
        }
    }
    
    adaptation_need = AdaptationNeed(
        system_id="web_server_01",
        reason="high_cpu_usage",
        urgency=0.8,
        detected_at=datetime.utcnow()
    )
    
    # Generate actions with full observability
    with tracer.trace_operation("pid_demo_execution") as span:
        span.add_tag("demo_type", "pid_controller")
        
        logger.info("Starting PID controller demonstration", extra={
            "system_id": adaptation_need.system_id,
            "cpu_usage": 85.0,
            "memory_usage": 75.0
        })
        
        actions = await pid_strategy.generate_actions(
            adaptation_need.system_id,
            current_state,
            adaptation_need
        )
        
        logger.info("PID demonstration completed", extra={
            "actions_generated": len(actions),
            "action_types": [action.action_type for action in actions]
        })
        
        span.add_tag("actions_generated", len(actions))
    
    # Display some metrics
    print(f"Generated {len(actions)} adaptation actions")
    for action in actions:
        print(f"  - {action.action_type}: {action.parameters}")
    
    # Show controller status
    status = pid_strategy.get_controller_status()
    print(f"PID Controllers: {status['controller_count']}")
    for name, controller_info in status['controllers'].items():
        print(f"  - {name}: setpoint={controller_info['setpoint']}, error={controller_info['state']['last_error']:.2f}")


async def demonstrate_llm_reasoning_observability():
    """Demonstrate LLM reasoning strategy observability features."""
    print("\n=== LLM Reasoning Strategy Observability Demo ===")
    
    logger = get_logger("example.llm_reasoning_demo")
    tracer = get_tracer()
    
    # Note: This is a mock demonstration since we don't have real LLM credentials
    # In a real scenario, you would configure actual LLM clients
    
    with tracer.trace_operation("llm_reasoning_demo") as span:
        span.add_tag("demo_type", "llm_reasoning")
        
        logger.info("Starting LLM reasoning demonstration", extra={
            "reasoning_type": "agentic",
            "max_iterations": 10
        })
        
        # Create mock reasoning context
        reasoning_context = ReasoningContext(
            system_id="api_gateway_01",
            current_state={
                "metrics": {
                    "response_time": MetricValue("response_time", 250.0, "ms"),
                    "error_rate": MetricValue("error_rate", 0.05, "ratio"),
                    "throughput": MetricValue("throughput", 1200.0, "req/min")
                }
            },
            historical_data=[
                {"timestamp": "2024-01-01T10:00:00Z", "response_time": 180.0},
                {"timestamp": "2024-01-01T10:05:00Z", "response_time": 220.0},
                {"timestamp": "2024-01-01T10:10:00Z", "response_time": 250.0}
            ],
            system_relationships={"dependencies": ["database", "cache"]}
        )
        
        logger.info("Mock LLM reasoning context prepared", extra={
            "system_id": reasoning_context.system_id,
            "metrics_count": len(reasoning_context.current_state.get("metrics", {})),
            "historical_points": len(reasoning_context.historical_data)
        })
        
        # In a real implementation, this would call the actual LLM reasoning strategy
        # For demo purposes, we'll just show the tracing structure
        
        with tracer.trace_operation("llm_api_simulation") as api_span:
            api_span.add_tag("provider", "openai")
            api_span.add_tag("model", "gpt-4")
            api_span.add_tag("operation", "reasoning")
            
            # Simulate API call delay
            await asyncio.sleep(0.1)
            
            api_span.add_tag("tokens_used", 1500)
            api_span.add_tag("confidence", 0.85)
        
        logger.info("LLM reasoning demonstration completed", extra={
            "reasoning_confidence": 0.85,
            "recommendations_generated": 2
        })
        
        span.add_tag("confidence", 0.85)
        span.add_tag("recommendations", 2)
    
    print("LLM reasoning simulation completed with full tracing")


async def demonstrate_llm_world_model_observability():
    """Demonstrate LLM world model observability features."""
    print("\n=== LLM World Model Observability Demo ===")
    
    logger = get_logger("example.llm_world_model_demo")
    tracer = get_tracer()
    
    with tracer.trace_operation("llm_world_model_demo") as span:
        span.add_tag("demo_type", "llm_world_model")
        
        logger.info("Starting LLM world model demonstration")
        
        # Create mock system state
        system_state = SystemState(
            system_id="microservice_cluster",
            timestamp=datetime.utcnow(),
            metrics={
                "cpu_usage": MetricValue("cpu_usage", 65.0, "percent"),
                "memory_usage": MetricValue("memory_usage", 70.0, "percent"),
                "request_rate": MetricValue("request_rate", 800.0, "req/min")
            },
            health_status=HealthStatus.HEALTHY
        )
        
        telemetry_event = TelemetryEvent(system_state)
        
        # Simulate world model operations with tracing
        with tracer.trace_operation("world_model_state_update") as update_span:
            update_span.add_tag("system_id", system_state.system_id)
            update_span.add_tag("metrics_count", len(system_state.metrics))
            
            logger.info("Processing system state update", extra={
                "system_id": system_state.system_id,
                "health_status": system_state.health_status.value,
                "cpu_usage": 65.0,
                "memory_usage": 70.0
            })
            
            # Simulate processing time
            await asyncio.sleep(0.05)
            
            update_span.add_tag("processing_complete", True)
        
        with tracer.trace_operation("world_model_prediction") as pred_span:
            pred_span.add_tag("system_id", system_state.system_id)
            pred_span.add_tag("time_horizon", 30)
            
            logger.info("Generating behavior prediction", extra={
                "system_id": system_state.system_id,
                "time_horizon_minutes": 30
            })
            
            # Simulate LLM prediction call
            await asyncio.sleep(0.2)
            
            pred_span.add_tag("prediction_confidence", 0.78)
            pred_span.add_tag("predicted_issues", 1)
        
        logger.info("LLM world model demonstration completed", extra={
            "operations_performed": 2,
            "prediction_confidence": 0.78
        })
        
        span.add_tag("operations_completed", 2)
    
    print("LLM world model simulation completed with comprehensive tracing")


async def demonstrate_correlation_tracking():
    """Demonstrate correlation ID tracking across components."""
    print("\n=== Correlation Tracking Demo ===")
    
    logger = get_logger("example.correlation_demo")
    tracer = get_tracer()
    
    # Start an adaptation flow with correlation tracking
    with tracer.trace_adaptation_flow("demo_adaptation", "distributed_system") as flow_span:
        correlation_id = flow_span.span_id
        
        with logger.correlation_context(correlation_id):
            logger.info("Starting correlated adaptation flow", extra={
                "adaptation_type": "performance_optimization",
                "target_system": "distributed_system"
            })
            
            # Simulate monitoring phase
            with tracer.trace_operation("monitoring_phase") as monitor_span:
                monitor_span.add_tag("phase", "monitor")
                logger.info("Collecting system metrics")
                await asyncio.sleep(0.02)
            
            # Simulate analysis phase with PID controller
            with tracer.trace_operation("analysis_phase") as analysis_span:
                analysis_span.add_tag("phase", "analyze")
                analysis_span.add_tag("strategy", "pid_reactive")
                logger.info("Analyzing metrics with PID controller")
                await asyncio.sleep(0.03)
            
            # Simulate LLM reasoning phase
            with tracer.trace_operation("reasoning_phase") as reasoning_span:
                reasoning_span.add_tag("phase", "reason")
                reasoning_span.add_tag("strategy", "llm_agentic")
                logger.info("Performing LLM-based reasoning")
                await asyncio.sleep(0.1)
            
            # Simulate execution phase
            with tracer.trace_operation("execution_phase") as exec_span:
                exec_span.add_tag("phase", "execute")
                logger.info("Executing adaptation actions")
                await asyncio.sleep(0.05)
            
            logger.info("Correlated adaptation flow completed", extra={
                "correlation_id": correlation_id,
                "phases_completed": 4
            })
    
    print(f"Adaptation flow completed with correlation ID: {correlation_id}")


async def display_metrics_summary():
    """Display a summary of collected metrics."""
    print("\n=== Metrics Summary ===")
    
    metrics = get_metrics_collector()
    all_metrics = metrics.get_all_metrics()
    
    print(f"Total metrics registered: {len(all_metrics)}")
    
    # Display some key metrics
    key_metrics = [
        "polaris_adaptations_triggered_total",
        "polaris_pid_controller_actions_total",
        "polaris_llm_api_calls_total",
        "polaris_system_health_score"
    ]
    
    for metric_name in key_metrics:
        if metric_name in all_metrics:
            metric = all_metrics[metric_name]
            print(f"  {metric_name}: {metric.get_type().value}")


async def main():
    """Run all enhanced observability demonstrations."""
    print("Enhanced POLARIS Observability Demonstration")
    print("=" * 50)
    
    # Initialize observability with development configuration
    config = create_development_config(service_name="polaris-enhanced-demo")
    observability_manager = initialize_observability(config)
    await observability_manager.initialize()
    
    try:
        # Run all demonstrations
        await demonstrate_pid_observability()
        await demonstrate_llm_reasoning_observability()
        await demonstrate_llm_world_model_observability()
        await demonstrate_correlation_tracking()
        await display_metrics_summary()
        
        print("\n" + "=" * 50)
        print("Enhanced observability demonstration completed!")
        print("All components now have comprehensive tracing, metrics, and logging.")
        
    except Exception as e:
        print(f"Demonstration failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        await shutdown_observability()


if __name__ == "__main__":
    asyncio.run(main())