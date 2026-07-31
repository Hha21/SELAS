"""
Observability Framework - Logging, Metrics, and Tracing

This module provides comprehensive observability capabilities including:
- Structured JSON logging with correlation IDs
- Metrics collection with Prometheus support
- Distributed tracing across component boundaries
- Automatic instrumentation and integration
"""

from .logging import PolarisLogger, LogLevel, LogFormatter, LogHandler, get_logger, configure_default_logging
from .metrics import PolarisMetricsCollector, MetricType, PrometheusExporter, get_metrics_collector
from .tracing import PolarisTracer, trace_polaris_method, TraceContext, get_tracer, configure_tracing
from .integration import (
    ObservabilityConfig, ObservabilityManager, observe_polaris_component,
    trace_adaptation_flow, trace_telemetry_processing, trace_world_model_operation,
    trace_connector_operation, initialize_observability, shutdown_observability,
    get_observability_manager
)
from .factory import (
    LoggerFactory, configure_logging, get_polaris_logger, is_logging_configured,
    get_logging_configuration, reset_logging, get_framework_logger, get_infrastructure_logger,
    get_adapter_logger, get_digital_twin_logger, get_control_logger, get_test_logger,
    TemporaryLoggingConfig
)

__all__ = [
    # Core observability components
    "PolarisLogger",
    "LogLevel", 
    "LogFormatter",
    "LogHandler",
    "get_logger",
    "configure_default_logging",
    "PolarisMetricsCollector",
    "MetricType",
    "PrometheusExporter",
    "get_metrics_collector",
    "PolarisTracer",
    "trace_polaris_method",
    "TraceContext",
    "get_tracer",
    "configure_tracing",
    
    # Integration and automation
    "ObservabilityConfig",
    "ObservabilityManager",
    "observe_polaris_component",
    "trace_adaptation_flow",
    "trace_telemetry_processing", 
    "trace_world_model_operation",
    "trace_connector_operation",
    "initialize_observability",
    "shutdown_observability",
    "get_observability_manager",
    
    # Logger factory and utilities
    "LoggerFactory",
    "configure_logging",
    "get_polaris_logger",
    "is_logging_configured",
    "get_logging_configuration",
    "reset_logging",
    "get_framework_logger",
    "get_infrastructure_logger",
    "get_adapter_logger",
    "get_digital_twin_logger",
    "get_control_logger",
    "get_test_logger",
    "TemporaryLoggingConfig",
]