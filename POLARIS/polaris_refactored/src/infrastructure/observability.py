"""
POLARIS Observability Infrastructure

Provides logging, metrics, and tracing capabilities for the POLARIS framework.
This is a simplified implementation for the SWIM system demo.
"""

import logging
import time
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from contextlib import contextmanager


@dataclass
class ObservabilityConfig:
    """Configuration for observability components."""
    service_name: str = "polaris"
    enable_metrics: bool = True
    enable_tracing: bool = True
    enable_logging: bool = True
    log_level: str = "INFO"


@dataclass
class MetricValue:
    """Represents a metric value."""
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MetricsCollector:
    """Simple metrics collector."""
    
    def __init__(self):
        self.metrics: Dict[str, List[MetricValue]] = {}
        self.counters: Dict[str, float] = {}
        self.gauges: Dict[str, float] = {}
    
    def record_counter(self, name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a counter metric."""
        key = f"{name}_{hash(str(sorted((tags or {}).items())))}"
        self.counters[key] = self.counters.get(key, 0) + value
    
    def record_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a gauge metric."""
        key = f"{name}_{hash(str(sorted((tags or {}).items())))}"
        self.gauges[key] = value
    
    def record_histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a histogram metric."""
        if name not in self.metrics:
            self.metrics[name] = []
        
        metric = MetricValue(name=name, value=value, labels=tags or {})
        self.metrics[name].append(metric)
        
        # Keep only last 1000 values
        if len(self.metrics[name]) > 1000:
            self.metrics[name] = self.metrics[name][-1000:]
    
    def set_active_systems_count(self, count: int) -> None:
        """Set the active systems count gauge."""
        self.record_gauge("polaris_active_systems", count)
    
    def get_metric(self, name: str) -> Optional[object]:
        """Get a metric by name (simplified)."""
        return self
    
    def increment(self, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment counter (for compatibility)."""
        pass
    
    def observe(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Observe histogram value (for compatibility)."""
        pass
    
    @contextmanager
    def time_telemetry_processing(self, system_id: str):
        """Context manager for timing telemetry processing."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.record_histogram("telemetry_processing_duration", duration, {"system_id": system_id})
    
    def register_counter(self, name: str, description: str, labels: List[str]) -> None:
        """Register a counter metric (for compatibility)."""
        pass
    
    def register_histogram(self, name: str, description: str, labels: List[str]) -> None:
        """Register a histogram metric (for compatibility)."""
        pass


class Tracer:
    """Simple tracer implementation."""
    
    def __init__(self):
        self.spans: List[Dict[str, Any]] = []
    
    @contextmanager
    def trace_operation(self, operation_name: str):
        """Context manager for tracing operations."""
        span = {
            "operation": operation_name,
            "start_time": time.time(),
            "tags": {},
            "error": None
        }
        
        class SpanContext:
            def add_tag(self, key: str, value: Any):
                span["tags"][key] = value
            
            def set_error(self, error: Exception):
                span["error"] = str(error)
        
        span_context = SpanContext()
        
        try:
            yield span_context
        except Exception as e:
            span_context.set_error(e)
            raise
        finally:
            span["end_time"] = time.time()
            span["duration"] = span["end_time"] - span["start_time"]
            self.spans.append(span)
            
            # Keep only last 1000 spans
            if len(self.spans) > 1000:
                self.spans = self.spans[-1000:]


class ObservabilityManager:
    """Manages observability components."""
    
    def __init__(self, config: ObservabilityConfig):
        self.config = config
        self.metrics_collector = MetricsCollector()
        self.tracer = Tracer()
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize observability components."""
        if self._initialized:
            return
        
        # Note: Logging setup is now handled by configure_logging() function
        # to avoid conflicts with framework configuration
        
        self._initialized = True
    
    def get_metrics_collector(self) -> MetricsCollector:
        """Get the metrics collector."""
        return self.metrics_collector
    
    def get_tracer(self) -> Tracer:
        """Get the tracer."""
        return self.tracer


# Global observability manager
_observability_manager: Optional[ObservabilityManager] = None


def initialize_observability(config: ObservabilityConfig) -> ObservabilityManager:
    """Initialize global observability."""
    global _observability_manager
    _observability_manager = ObservabilityManager(config)
    return _observability_manager


async def shutdown_observability() -> None:
    """Shutdown observability."""
    global _observability_manager
    _observability_manager = None


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


def get_framework_logger(name: str) -> logging.Logger:
    """Get a framework logger instance."""
    return logging.getLogger(f"polaris.framework.{name}")


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector."""
    if _observability_manager:
        return _observability_manager.get_metrics_collector()
    return MetricsCollector()


def get_tracer() -> Tracer:
    """Get the global tracer."""
    if _observability_manager:
        return _observability_manager.get_tracer()
    return Tracer()


class PolarisTextFormatter(logging.Formatter):
    """Custom text formatter that handles structured logging with extra fields."""
    
    def format(self, record):
        # Start with the basic format
        formatted = super().format(record)
        
        # Add extra fields if they exist
        if hasattr(record, '__dict__'):
            extra_fields = []
            for key, value in record.__dict__.items():
                # Skip standard logging fields
                if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                              'filename', 'module', 'lineno', 'funcName', 'created', 'msecs',
                              'relativeCreated', 'thread', 'threadName', 'processName', 'process',
                              'getMessage', 'exc_info', 'exc_text', 'stack_info', 'asctime']:
                    extra_fields.append(f"{key}={value}")
            
            if extra_fields:
                formatted += f" [{', '.join(extra_fields)}]"
        
        return formatted


class PolarisJSONFormatter(logging.Formatter):
    """Custom JSON formatter that handles structured logging with extra fields."""
    
    def format(self, record):
        import json
        from datetime import datetime
        
        # Build the log entry
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        
        # Add extra fields if they exist
        if hasattr(record, '__dict__'):
            extra = {}
            for key, value in record.__dict__.items():
                # Skip standard logging fields
                if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                              'filename', 'module', 'lineno', 'funcName', 'created', 'msecs',
                              'relativeCreated', 'thread', 'threadName', 'processName', 'process',
                              'getMessage', 'exc_info', 'exc_text', 'stack_info']:
                    extra[key] = value
            
            if extra:
                log_entry["extra"] = extra
        
        return json.dumps(log_entry, default=str)


def configure_logging(config: Any) -> None:
    """Configure logging from config."""
    import logging.config
    
    level = getattr(config, 'level', 'INFO')
    format_type = getattr(config, 'format', 'text')
    output = getattr(config, 'output', 'console')
    file_path = getattr(config, 'file_path', None)
    
    # Clear any existing handlers to avoid conflicts
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Define formatters based on format type
    if format_type.lower() == 'json':
        formatter = PolarisJSONFormatter()
    else:
        # Text formatter (default) - handles structured logging properly
        formatter = PolarisTextFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Configure handlers based on output setting
    handlers = []
    
    if output in ['console', 'both']:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)
    
    if output in ['file', 'both'] and file_path:
        try:
            from pathlib import Path
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(file_path)
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)
        except Exception as e:
            print(f"Warning: Could not create file handler for {file_path}: {e}")
    
    # Apply configuration
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        handlers=handlers,
        force=True  # Force reconfiguration
    )


# Decorators for observability
def observe_polaris_component(component_name: str, auto_trace: bool = False, auto_metrics: bool = False, log_method_calls: bool = False):
    """Decorator for observing POLARIS components."""
    def decorator(cls):
        if auto_trace or auto_metrics or log_method_calls:
            # Add observability to class methods
            for attr_name in dir(cls):
                attr = getattr(cls, attr_name)
                if callable(attr) and not attr_name.startswith('_'):
                    setattr(cls, attr_name, _wrap_method_with_observability(attr, component_name, auto_trace, auto_metrics, log_method_calls))
        return cls
    return decorator


def trace_adaptation_flow(operation_name: str):
    """Decorator for tracing adaptation flows."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.trace_operation(operation_name):
                return await func(*args, **kwargs)
        return wrapper
    return decorator


def trace_world_model_operation(operation_name: str):
    """Decorator for tracing world model operations."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.trace_operation(f"world_model_{operation_name}"):
                return await func(*args, **kwargs)
        return wrapper
    return decorator


def _wrap_method_with_observability(method, component_name: str, auto_trace: bool, auto_metrics: bool, log_method_calls: bool):
    """Wrap a method with observability features."""
    @wraps(method)
    async def async_wrapper(*args, **kwargs):
        logger = get_logger(f"polaris.{component_name}")
        
        if log_method_calls:
            logger.debug(f"Calling {method.__name__}")
        
        start_time = time.time()
        
        try:
            if auto_trace:
                tracer = get_tracer()
                with tracer.trace_operation(f"{component_name}.{method.__name__}"):
                    result = await method(*args, **kwargs)
            else:
                result = await method(*args, **kwargs)
            
            if auto_metrics:
                duration = time.time() - start_time
                metrics = get_metrics_collector()
                metrics.record_histogram(f"{component_name}_method_duration", duration, {"method": method.__name__})
            
            return result
            
        except Exception as e:
            if log_method_calls:
                logger.error(f"Error in {method.__name__}: {e}")
            raise
    
    @wraps(method)
    def sync_wrapper(*args, **kwargs):
        logger = get_logger(f"polaris.{component_name}")
        
        if log_method_calls:
            logger.debug(f"Calling {method.__name__}")
        
        start_time = time.time()
        
        try:
            result = method(*args, **kwargs)
            
            if auto_metrics:
                duration = time.time() - start_time
                metrics = get_metrics_collector()
                metrics.record_histogram(f"{component_name}_method_duration", duration, {"method": method.__name__})
            
            return result
            
        except Exception as e:
            if log_method_calls:
                logger.error(f"Error in {method.__name__}: {e}")
            raise
    
    # Return appropriate wrapper based on whether method is async
    import asyncio
    if asyncio.iscoroutinefunction(method):
        return async_wrapper
    else:
        return sync_wrapper