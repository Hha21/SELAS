"""
Centralized Logger Factory for POLARIS Framework

This module provides a centralized factory for creating and managing POLARIS loggers
with consistent configuration across all framework components.
"""

from typing import Optional, Dict, Any, TYPE_CHECKING
from pathlib import Path
import threading

from .logging import (
    PolarisLogger, LogLevel, get_logger, configure_default_logging,
    JSONLogFormatter, HumanReadableFormatter, ConsoleLogHandler, FileLogHandler
)

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    from ...framework.configuration.models import LoggingConfiguration


class LoggerFactory:
    """
    Centralized factory for creating and managing POLARIS loggers.
    
    Features:
    - Consistent logger configuration across components
    - Centralized configuration management
    - Thread-safe logger creation and caching
    - Dynamic reconfiguration support
    - Integration with POLARIS configuration system
    """
    
    _instance: Optional['LoggerFactory'] = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._loggers: Dict[str, PolarisLogger] = {}
        self._config: Optional[LoggingConfiguration] = None
        self._configured = False
        self._config_lock = threading.RLock()
    
    @classmethod
    def get_instance(cls) -> 'LoggerFactory':
        """Get singleton instance of LoggerFactory."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = LoggerFactory()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (useful for testing)."""
        with cls._lock:
            cls._instance = None
    
    def configure(self, config: 'LoggingConfiguration') -> None:
        """
        Configure the logger factory with framework logging settings.
        
        Args:
            config: Logging configuration from framework configuration
        """
        with self._config_lock:
            self._config = config
            self._configured = True
            
            # Configure default logging system
            log_level = LogLevel(config.level.upper())
            use_json = (config.format.lower() == "json")
            log_file = None
            
            if config.output in ["file", "both"] and config.file_path:
                log_file = Path(config.file_path)
            
            configure_default_logging(
                level=log_level,
                use_json=use_json,
                log_file=log_file
            )
            
            # Reconfigure existing loggers
            self._reconfigure_existing_loggers()
    
    def get_logger(
        self, 
        name: str, 
        level: Optional[LogLevel] = None,
        config_override: Optional['LoggingConfiguration'] = None
    ) -> PolarisLogger:
        """
        Get or create a logger with the specified name and configuration.
        
        Args:
            name: Logger name (e.g., "polaris.framework", "polaris.adapter.test")
            level: Optional log level override
            config_override: Optional configuration override for this logger
            
        Returns:
            PolarisLogger: Configured logger instance
        """
        with self._config_lock:
            # Determine effective configuration
            effective_config = config_override or self._config
            effective_level = level
            
            if effective_level is None and effective_config:
                effective_level = LogLevel(effective_config.level.upper())
            elif effective_level is None:
                effective_level = LogLevel.INFO

            if effective_config and effective_level:
                effective_config.level = effective_level.name.upper()
            
            # Get or create logger
            if name in self._loggers:
                logger = self._loggers[name]
                # Only reconfigure if there's a config override or level override
                if config_override:
                    self._apply_config_to_logger(logger, config_override)
                if level is not None:
                    logger.set_level(level)
            else:
                logger = get_logger(name, effective_level)
                self._loggers[name] = logger
                # Apply configuration for new loggers
                if effective_config:
                    self._apply_config_to_logger(logger, effective_config)
            
            return logger
    
    def _apply_config_to_logger(self, logger: PolarisLogger, config: 'LoggingConfiguration') -> None:
        """Apply configuration to a specific logger."""
        # Clear existing handlers
        logger.handlers.clear()
        
        # Set log level
        logger.set_level(LogLevel(config.level.upper()))
        
        # Create formatter
        if config.format.lower() == "json":
            formatter = JSONLogFormatter()
        else:
            formatter = HumanReadableFormatter()
        
        # Add console handler if needed
        if config.output in ["console", "both"]:
            console_handler = ConsoleLogHandler(formatter)
            logger.add_handler(console_handler)
        
        # Add file handler if needed
        if config.output in ["file", "both"] and config.file_path:
            file_handler = FileLogHandler(formatter, config.file_path)
            logger.add_handler(file_handler)
    
    def _reconfigure_existing_loggers(self) -> None:
        """Reconfigure all existing loggers with current configuration."""
        if not self._config:
            return
        
        for logger in self._loggers.values():
            self._apply_config_to_logger(logger, self._config)
    
    def get_configuration(self) -> Optional['LoggingConfiguration']:
        """Get current logging configuration."""
        with self._config_lock:
            return self._config
    
    def is_configured(self) -> bool:
        """Check if factory has been configured."""
        with self._config_lock:
            return self._configured
    
    def get_logger_names(self) -> list[str]:
        """Get list of all created logger names."""
        with self._config_lock:
            return list(self._loggers.keys())
    
    def reset(self) -> None:
        """Reset factory state (useful for testing)."""
        with self._config_lock:
            self._loggers.clear()
            self._config = None
            self._configured = False


# Convenience functions for global access
def configure_logging(config: 'LoggingConfiguration') -> None:
    """Configure global logging using the factory."""
    factory = LoggerFactory.get_instance()
    factory.configure(config)


def get_polaris_logger(
    name: str, 
    level: Optional[LogLevel] = None,
    config_override: Optional['LoggingConfiguration'] = None
) -> PolarisLogger:
    """
    Get a POLARIS logger using the global factory.
    
    Args:
        name: Logger name
        level: Optional log level override
        config_override: Optional configuration override
        
    Returns:
        PolarisLogger: Configured logger instance
    """
    factory = LoggerFactory.get_instance()
    return factory.get_logger(name, level, config_override)


def is_logging_configured() -> bool:
    """Check if global logging has been configured."""
    factory = LoggerFactory.get_instance()
    return factory.is_configured()


def get_logging_configuration() -> Optional['LoggingConfiguration']:
    """Get current global logging configuration."""
    factory = LoggerFactory.get_instance()
    return factory.get_configuration()


def reset_logging() -> None:
    """Reset global logging state (useful for testing)."""
    factory = LoggerFactory.get_instance()
    factory.reset()


# Component-specific logger creation helpers
def get_framework_logger(component: str) -> PolarisLogger:
    """Get a logger for framework components."""
    return get_polaris_logger(f"polaris.framework.{component}")


def get_infrastructure_logger(component: str) -> PolarisLogger:
    """Get a logger for infrastructure components."""
    return get_polaris_logger(f"polaris.infrastructure.{component}")


def get_adapter_logger(adapter_id: str) -> PolarisLogger:
    """Get a logger for adapter components."""
    return get_polaris_logger(f"polaris.adapter.{adapter_id}")


def get_digital_twin_logger(component: str) -> PolarisLogger:
    """Get a logger for digital twin components."""
    return get_polaris_logger(f"polaris.digital_twin.{component}")


def get_control_logger(component: str) -> PolarisLogger:
    """Get a logger for control and reasoning components."""
    return get_polaris_logger(f"polaris.control.{component}")


def get_test_logger(test_name: str) -> PolarisLogger:
    """Get a logger for test components."""
    return get_polaris_logger(f"polaris.test.{test_name}")


# Context manager for temporary logging configuration
class TemporaryLoggingConfig:
    """Context manager for temporary logging configuration changes."""
    
    def __init__(self, config: 'LoggingConfiguration'):
        self.config = config
        self.original_config = None
        self.factory = LoggerFactory.get_instance()
    
    def __enter__(self):
        self.original_config = self.factory.get_configuration()
        self.factory.configure(self.config)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.original_config:
            self.factory.configure(self.original_config)
        else:
            self.factory.reset()