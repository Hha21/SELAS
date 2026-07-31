"""
Digital Twin Logging and Debugging Support.

This module provides specialized logging functionality for the Digital Twin
component, including development-friendly console output, detailed file logging,
operation timing, and debugging context.
"""

import logging
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union, Callable, List
from contextlib import contextmanager
from functools import wraps

from .logging_setup import PrettyColoredFormatter, JsonFormatter


class DigitalTwinFormatter(PrettyColoredFormatter):
    """
    Enhanced formatter for Digital Twin with operation context and timing.
    
    Format:
    2025-08-13 14:35:12.345 UTC | INFO     | digital_twin:123 | [QUERY-abc123] query_state | Processing natural language query | 45ms
    """
    
    def format(self, record: logging.LogRecord) -> str:
        # Get base formatted message
        base_message = super().format(record)
        
        # Add operation context if available
        operation_id = getattr(record, 'operation_id', None)
        operation_type = getattr(record, 'operation_type', None)
        duration_ms = getattr(record, 'duration_ms', None)
        
        if operation_id or operation_type or duration_ms:
            context_parts = []
            
            if operation_id:
                context_parts.append(f"[{operation_id}]")
            
            if operation_type:
                context_parts.append(operation_type)
            
            if duration_ms is not None:
                context_parts.append(f"{duration_ms:.1f}ms")
            
            if context_parts:
                # Insert context before the message part
                parts = base_message.split(" | ")
                if len(parts) >= 4:
                    context_str = " | ".join(context_parts)
                    parts.insert(-1, context_str)
                    return " | ".join(parts)
        
        return base_message


class DigitalTwinJsonFormatter(JsonFormatter):
    """Enhanced JSON formatter for Digital Twin with structured operation data."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Get base JSON structure
        base_data = json.loads(super().format(record))
        
        # Add Digital Twin specific fields
        dt_fields = {}
        
        # Operation context
        if hasattr(record, 'operation_id'):
            dt_fields['operation_id'] = record.operation_id
        if hasattr(record, 'operation_type'):
            dt_fields['operation_type'] = record.operation_type
        if hasattr(record, 'duration_ms'):
            dt_fields['duration_ms'] = record.duration_ms
        
        # World Model context
        if hasattr(record, 'world_model_type'):
            dt_fields['world_model_type'] = record.world_model_type
        if hasattr(record, 'confidence'):
            dt_fields['confidence'] = record.confidence
        
        # Request/Response context
        if hasattr(record, 'request_id'):
            dt_fields['request_id'] = record.request_id
        if hasattr(record, 'query_type'):
            dt_fields['query_type'] = record.query_type
        if hasattr(record, 'simulation_type'):
            dt_fields['simulation_type'] = record.simulation_type
        
        # Performance metrics
        if hasattr(record, 'memory_usage_mb'):
            dt_fields['memory_usage_mb'] = record.memory_usage_mb
        if hasattr(record, 'cpu_percent'):
            dt_fields['cpu_percent'] = record.cpu_percent
        
        # Error context
        if hasattr(record, 'error_code'):
            dt_fields['error_code'] = record.error_code
        if hasattr(record, 'error_context'):
            dt_fields['error_context'] = record.error_context
        
        # Merge Digital Twin fields
        if dt_fields:
            base_data['digital_twin'] = dt_fields
        
        return json.dumps(base_data, separators=(",", ":"))


class OperationTimer:
    """Context manager for timing operations with automatic logging."""
    
    def __init__(
        self,
        logger: logging.Logger,
        operation_type: str,
        operation_id: Optional[str] = None,
        log_level: int = logging.INFO,
        extra_context: Optional[Dict[str, Any]] = None
    ):
        """Initialize operation timer.
        
        Args:
            logger: Logger instance to use
            operation_type: Type of operation being timed
            operation_id: Optional unique identifier for the operation
            log_level: Log level for timing messages
            extra_context: Additional context to include in logs
        """
        self.logger = logger
        self.operation_type = operation_type
        self.operation_id = operation_id or f"{operation_type}-{int(time.time() * 1000)}"
        self.log_level = log_level
        self.extra_context = extra_context or {}
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        """Start timing the operation."""
        self.start_time = time.time()
        
        self.logger.log(
            self.log_level,
            f"Starting {self.operation_type}",
            extra={
                'operation_id': self.operation_id,
                'operation_type': self.operation_type,
                **self.extra_context
            }
        )
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """End timing and log results."""
        self.end_time = time.time()
        duration_ms = (self.end_time - self.start_time) * 1000
        
        if exc_type is None:
            # Success
            self.logger.log(
                self.log_level,
                f"Completed {self.operation_type}",
                extra={
                    'operation_id': self.operation_id,
                    'operation_type': self.operation_type,
                    'duration_ms': duration_ms,
                    **self.extra_context
                }
            )
        else:
            # Error occurred
            self.logger.error(
                f"Failed {self.operation_type}: {exc_val}",
                extra={
                    'operation_id': self.operation_id,
                    'operation_type': self.operation_type,
                    'duration_ms': duration_ms,
                    'error_type': exc_type.__name__ if exc_type else None,
                    'error_message': str(exc_val) if exc_val else None,
                    **self.extra_context
                },
                exc_info=True
            )
    
    @property
    def duration_ms(self) -> Optional[float]:
        """Get operation duration in milliseconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return None


def timed_operation(
    operation_type: str,
    log_level: int = logging.INFO,
    include_args: bool = False,
    include_result: bool = False
):
    """Decorator for automatically timing and logging function calls.
    
    Args:
        operation_type: Type of operation for logging
        log_level: Log level for timing messages
        include_args: Whether to include function arguments in logs
        include_result: Whether to include function result in logs
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Get logger from first argument if it's a class instance
            logger = None
            if args and hasattr(args[0], 'logger'):
                logger = args[0].logger
            else:
                logger = logging.getLogger(func.__module__)
            
            # Prepare extra context
            extra_context = {}
            if include_args:
                extra_context['function_args'] = str(args[1:])  # Skip self
                extra_context['function_kwargs'] = kwargs
            
            operation_id = f"{func.__name__}-{int(time.time() * 1000)}"
            
            with OperationTimer(
                logger=logger,
                operation_type=operation_type,
                operation_id=operation_id,
                log_level=log_level,
                extra_context=extra_context
            ):
                result = await func(*args, **kwargs)
                
                if include_result and result is not None:
                    logger.log(
                        log_level,
                        f"Operation result available",
                        extra={
                            'operation_id': operation_id,
                            'operation_type': operation_type,
                            'result_type': type(result).__name__,
                            'result_summary': str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
                        }
                    )
                
                return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Get logger from first argument if it's a class instance
            logger = None
            if args and hasattr(args[0], 'logger'):
                logger = args[0].logger
            else:
                logger = logging.getLogger(func.__module__)
            
            # Prepare extra context
            extra_context = {}
            if include_args:
                extra_context['function_args'] = str(args[1:])  # Skip self
                extra_context['function_kwargs'] = kwargs
            
            operation_id = f"{func.__name__}-{int(time.time() * 1000)}"
            
            with OperationTimer(
                logger=logger,
                operation_type=operation_type,
                operation_id=operation_id,
                log_level=log_level,
                extra_context=extra_context
            ):
                result = func(*args, **kwargs)
                
                if include_result and result is not None:
                    logger.log(
                        log_level,
                        f"Operation result available",
                        extra={
                            'operation_id': operation_id,
                            'operation_type': operation_type,
                            'result_type': type(result).__name__,
                            'result_summary': str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
                        }
                    )
                
                return result
        
        # Return appropriate wrapper based on whether function is async
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


class DigitalTwinLogger:
    """
    Specialized logger for Digital Twin component with development and debugging features.
    
    Provides both console and file logging with operation timing, context tracking,
    and debugging support.
    """
    
    def __init__(
        self,
        name: str = "digital_twin",
        console_level: Union[str, int] = logging.INFO,
        file_level: Union[str, int] = logging.DEBUG,
        log_file: Optional[Union[str, Path]] = None,
        enable_console: bool = True,
        enable_file: bool = True,
        console_format: str = "pretty",  # "pretty" or "json"
        file_format: str = "json"  # "pretty" or "json"
    ):
        """Initialize Digital Twin logger.
        
        Args:
            name: Logger name
            console_level: Console logging level
            file_level: File logging level
            log_file: Path to log file (auto-generated if None)
            enable_console: Enable console logging
            enable_file: Enable file logging
            console_format: Console log format ("pretty" or "json")
            file_format: File log format ("pretty" or "json")
        """
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)  # Set to lowest level, handlers will filter
        
        # Clear existing handlers
        self.logger.handlers.clear()
        self.logger.propagate = False
        
        # Setup console handler
        if enable_console:
            self._setup_console_handler(console_level, console_format)
        
        # Setup file handler
        if enable_file:
            if log_file is None:
                log_file = Path("logs") / f"{name}.log"
            self._setup_file_handler(file_level, file_format, log_file)
        
        # Log initialization
        self.logger.info(
            f"Digital Twin logger initialized",
            extra={
                'logger_name': name,
                'console_enabled': enable_console,
                'file_enabled': enable_file,
                'console_level': logging.getLevelName(console_level) if isinstance(console_level, int) else console_level,
                'file_level': logging.getLevelName(file_level) if isinstance(file_level, int) else file_level
            }
        )
    
    def _setup_console_handler(self, level: Union[str, int], format_type: str) -> None:
        """Setup console logging handler."""
        import sys
        
        handler = logging.StreamHandler(sys.stdout)
        
        if isinstance(level, str):
            level = getattr(logging, level.upper())
        handler.setLevel(level)
        
        if format_type.lower() == "pretty":
            handler.setFormatter(DigitalTwinFormatter())
        elif format_type.lower() == "json":
            handler.setFormatter(DigitalTwinJsonFormatter())
        else:
            raise ValueError(f"Unknown console format: {format_type}")
        
        self.logger.addHandler(handler)
    
    def _setup_file_handler(
        self,
        level: Union[str, int],
        format_type: str,
        log_file: Union[str, Path]
    ) -> None:
        """Setup file logging handler."""
        log_file = Path(log_file)
        
        # Create log directory if it doesn't exist
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        
        if isinstance(level, str):
            level = getattr(logging, level.upper())
        handler.setLevel(level)
        
        if format_type.lower() == "pretty":
            handler.setFormatter(DigitalTwinFormatter())
        elif format_type.lower() == "json":
            handler.setFormatter(DigitalTwinJsonFormatter())
        else:
            raise ValueError(f"Unknown file format: {format_type}")
        
        self.logger.addHandler(handler)
    
    def get_logger(self) -> logging.Logger:
        """Get the underlying logger instance."""
        return self.logger
    
    @contextmanager
    def operation_context(
        self,
        operation_type: str,
        operation_id: Optional[str] = None,
        **context
    ):
        """Context manager for operation logging with automatic timing.
        
        Args:
            operation_type: Type of operation
            operation_id: Optional operation identifier
            **context: Additional context to include in logs
        """
        with OperationTimer(
            logger=self.logger,
            operation_type=operation_type,
            operation_id=operation_id,
            extra_context=context
        ) as timer:
            yield timer
    
    def log_world_model_operation(
        self,
        operation_type: str,
        model_type: str,
        request_id: str,
        success: bool,
        duration_ms: float,
        confidence: Optional[float] = None,
        error_message: Optional[str] = None,
        **extra_context
    ) -> None:
        """Log World Model operation with structured context.
        
        Args:
            operation_type: Type of operation (query, simulate, diagnose)
            model_type: World Model implementation type
            request_id: Request identifier
            success: Whether operation succeeded
            duration_ms: Operation duration in milliseconds
            confidence: Confidence score if available
            error_message: Error message if operation failed
            **extra_context: Additional context
        """
        level = logging.INFO if success else logging.ERROR
        message = f"World Model {operation_type} {'completed' if success else 'failed'}"
        
        extra = {
            'operation_type': operation_type,
            'world_model_type': model_type,
            'request_id': request_id,
            'duration_ms': duration_ms,
            'success': success,
            **extra_context
        }
        
        if confidence is not None:
            extra['confidence'] = confidence
        
        if error_message:
            extra['error_message'] = error_message
        
        self.logger.log(level, message, extra=extra)
    
    def log_nats_event(
        self,
        event_type: str,
        subject: str,
        message_id: Optional[str] = None,
        success: bool = True,
        processing_time_ms: Optional[float] = None,
        error_message: Optional[str] = None,
        **extra_context
    ) -> None:
        """Log NATS event processing with structured context.
        
        Args:
            event_type: Type of event (update, calibrate)
            subject: NATS subject
            message_id: Message identifier if available
            success: Whether processing succeeded
            processing_time_ms: Processing time in milliseconds
            error_message: Error message if processing failed
            **extra_context: Additional context
        """
        level = logging.DEBUG if success else logging.ERROR
        message = f"NATS {event_type} event {'processed' if success else 'failed'}"
        
        extra = {
            'event_type': event_type,
            'nats_subject': subject,
            'success': success,
            **extra_context
        }
        
        if message_id:
            extra['message_id'] = message_id
        
        if processing_time_ms is not None:
            extra['processing_time_ms'] = processing_time_ms
        
        if error_message:
            extra['error_message'] = error_message
        
        self.logger.log(level, message, extra=extra)
    
    def log_grpc_request(
        self,
        method: str,
        request_id: str,
        success: bool,
        duration_ms: float,
        response_size_bytes: Optional[int] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        **extra_context
    ) -> None:
        """Log gRPC request with structured context.
        
        Args:
            method: gRPC method name
            request_id: Request identifier
            success: Whether request succeeded
            duration_ms: Request duration in milliseconds
            response_size_bytes: Response size in bytes
            error_code: gRPC error code if request failed
            error_message: Error message if request failed
            **extra_context: Additional context
        """
        level = logging.INFO if success else logging.ERROR
        message = f"gRPC {method} {'completed' if success else 'failed'}"
        
        extra = {
            'grpc_method': method,
            'request_id': request_id,
            'duration_ms': duration_ms,
            'success': success,
            **extra_context
        }
        
        if response_size_bytes is not None:
            extra['response_size_bytes'] = response_size_bytes
        
        if error_code:
            extra['error_code'] = error_code
        
        if error_message:
            extra['error_message'] = error_message
        
        self.logger.log(level, message, extra=extra)
    
    def log_configuration_event(
        self,
        event_type: str,
        config_section: str,
        success: bool = True,
        details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Log configuration-related events.
        
        Args:
            event_type: Type of configuration event (load, validate, update)
            config_section: Configuration section affected
            success: Whether event succeeded
            details: Configuration details (sensitive data will be masked)
            error_message: Error message if event failed
        """
        level = logging.INFO if success else logging.ERROR
        message = f"Configuration {event_type} for {config_section} {'completed' if success else 'failed'}"
        
        extra = {
            'config_event_type': event_type,
            'config_section': config_section,
            'success': success
        }
        
        if details:
            # Mask sensitive configuration data
            masked_details = self._mask_sensitive_config(details)
            extra['config_details'] = masked_details
        
        if error_message:
            extra['error_message'] = error_message
        
        self.logger.log(level, message, extra=extra)
    
    def _mask_sensitive_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive configuration data for logging.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Configuration with sensitive data masked
        """
        sensitive_keys = {
            'api_key', 'api_key_env', 'password', 'secret', 'token',
            'private_key', 'credential', 'auth'
        }
        
        masked = {}
        for key, value in config.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                if isinstance(value, str) and value:
                    masked[key] = f"***{value[-4:]}" if len(value) > 4 else "***"
                else:
                    masked[key] = "***"
            elif isinstance(value, dict):
                masked[key] = self._mask_sensitive_config(value)
            else:
                masked[key] = value
        
        return masked
    
    def log_performance_metrics(
        self,
        operation_type: str,
        metrics: Dict[str, Union[int, float]],
        thresholds: Optional[Dict[str, Union[int, float]]] = None
    ) -> None:
        """Log performance metrics with optional threshold checking.
        
        Args:
            operation_type: Type of operation the metrics relate to
            metrics: Performance metrics dictionary
            thresholds: Optional thresholds for alerting
        """
        # Check for threshold violations
        violations = []
        if thresholds:
            for metric, value in metrics.items():
                if metric in thresholds and value > thresholds[metric]:
                    violations.append(f"{metric}={value} > {thresholds[metric]}")
        
        level = logging.WARNING if violations else logging.INFO
        message = f"Performance metrics for {operation_type}"
        
        if violations:
            message += f" (THRESHOLD VIOLATIONS: {', '.join(violations)})"
        
        self.logger.log(
            level,
            message,
            extra={
                'operation_type': operation_type,
                'performance_metrics': metrics,
                'threshold_violations': violations if violations else None
            }
        )
    
    def log_debugging_info(
        self,
        context: str,
        debug_data: Dict[str, Any],
        suggestions: Optional[List[str]] = None
    ) -> None:
        """Log debugging information with context and suggestions.
        
        Args:
            context: Debugging context description
            debug_data: Debug data dictionary
            suggestions: Optional debugging suggestions
        """
        message = f"Debug info: {context}"
        
        extra = {
            'debug_context': context,
            'debug_data': debug_data
        }
        
        if suggestions:
            extra['debug_suggestions'] = suggestions
            message += f" (Suggestions: {', '.join(suggestions)})"
        
        self.logger.debug(message, extra=extra)


def setup_digital_twin_logging(config: Dict[str, Any]) -> DigitalTwinLogger:
    """Setup Digital Twin logging based on configuration.
    
    Args:
        config: Digital Twin configuration dictionary
        
    Returns:
        Configured DigitalTwinLogger instance
    """
    debugging_config = config.get("debugging", {})
    
    # Extract logging configuration
    log_level = debugging_config.get("log_level", "INFO").upper()
    enable_detailed_logging = debugging_config.get("enable_detailed_logging", True)
    log_to_console = debugging_config.get("log_to_console", True)
    log_file = debugging_config.get("log_file", "logs/digital_twin.log")
    
    # Convert log level string to logging constant
    console_level = getattr(logging, log_level, logging.INFO)
    file_level = logging.DEBUG if enable_detailed_logging else console_level
    
    return DigitalTwinLogger(
        name="digital_twin",
        console_level=console_level,
        file_level=file_level,
        log_file=log_file,
        enable_console=log_to_console,
        enable_file=True,
        console_format="pretty",
        file_format="json"
    )