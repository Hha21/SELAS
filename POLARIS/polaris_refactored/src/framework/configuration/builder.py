"""
Configuration Builder

Provides a fluent interface for building POLARIS configurations from multiple sources.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from .core import PolarisConfiguration
from .sources import ConfigurationSource, YAMLConfigurationSource, EnvironmentConfigurationSource


class ConfigurationBuilder:
    """
    Builder for creating POLARIS configurations from multiple sources.
    
    Provides a fluent interface for adding configuration sources and building
    the final configuration with proper priority handling.
    """
    
    def __init__(self):
        self.sources: List[ConfigurationSource] = []
        self._hot_reload_enabled = False
    
    def add_yaml_source(self, path: Union[str, Path], priority: int = 100) -> 'ConfigurationBuilder':
        """
        Add a YAML configuration source.
        
        Args:
            path: Path to YAML configuration file
            priority: Priority of this source (higher = more important)
            
        Returns:
            Self for method chaining
        """
        source = YAMLConfigurationSource(path, priority)
        self.sources.append(source)
        return self
    
    def add_environment_source(self, prefix: str = "POLARIS_", priority: int = 200, validate: bool = True) -> 'ConfigurationBuilder':
        """
        Add an environment variable configuration source.
        
        Args:
            prefix: Prefix for environment variables
            priority: Priority of this source (higher = more important)
            validate: Whether to validate environment variables
            
        Returns:
            Self for method chaining
        """
        source = EnvironmentConfigurationSource(prefix, priority, validate)
        self.sources.append(source)
        return self
    
    def add_source(self, source: ConfigurationSource) -> 'ConfigurationBuilder':
        """
        Add a custom configuration source.
        
        Args:
            source: Configuration source to add
            
        Returns:
            Self for method chaining
        """
        self.sources.append(source)
        return self
    
    def add_defaults(self) -> 'ConfigurationBuilder':
        """
        Add default configuration values.
        
        Returns:
            Self for method chaining
        """
        # Create a simple default configuration source
        defaults = {
            "framework": {
                "service_name": "polaris",
                "version": "2.0.0",
                "environment": "development",
                "nats_config": {
                    "servers": ["nats://localhost:4222"],
                    "timeout": 30
                },
                "telemetry_config": {
                    "enabled": True,
                    "collection_interval": 30,
                    "batch_size": 100,
                    "retention_days": 30
                },
                "logging_config": {
                    "level": "INFO",
                    "format": "text",
                    "output": "console",
                    "max_file_size": 10485760,
                    "backup_count": 5
                },
                "plugin_search_paths": ["./plugins"],
                "max_concurrent_adaptations": 10,
                "adaptation_timeout": 300
            },
            "managed_systems": {},
            "llm": {
                "provider": "mock",
                "api_endpoint": "http://localhost:8000",
                "model_name": "mock-model",
                "max_tokens": 1000,
                "temperature": 0.1,
                "timeout": 30.0,
                "max_retries": 3,
                "cache_ttl": 300,
                "enable_function_calling": True
            },
            "control_reasoning": {
                "adaptive_controller": {
                    "enabled": True,
                    "control_strategies": ["threshold_reactive"]
                },
                "threshold_reactive": {
                    "enabled": True,
                    "enable_multi_metric_evaluation": True,
                    "action_prioritization_enabled": True,
                    "max_concurrent_actions": 5,
                    "default_cooldown_seconds": 60.0,
                    "enable_fallback": True,
                    "rules": []
                }
            },
            "digital_twin": {
                "world_model": {
                    "type": "statistical",
                    "conversation_history_limit": 10
                },
                "knowledge_base": {
                    "enabled": True,
                    "max_patterns": 1000
                },
                "learning_engine": {
                    "enabled": True,
                    "learning_strategies": ["pattern_recognition"]
                }
            },
            "data_storage": {
                "backends": {
                    "time_series": "in_memory",
                    "document": "in_memory",
                    "graph": "in_memory"
                }
            },
            "event_bus": {
                "max_queue_size": 5000,
                "worker_count": 4
            },
            "observability": {
                "service_name": "polaris",
                "enable_metrics": True,
                "enable_tracing": True,
                "enable_logging": True
            }
        }
        
        # Create a simple source for defaults
        class DefaultConfigurationSource(ConfigurationSource):
            def __init__(self, defaults: Dict[str, Any]):
                self.defaults = defaults
                self._priority = 0
            
            async def load(self) -> Dict[str, Any]:
                return self.defaults
            
            def get_priority(self) -> int:
                return self._priority
            
            def has_changed(self) -> bool:
                return False
        
        self.sources.append(DefaultConfigurationSource(defaults))
        return self
    
    def enable_hot_reload(self, enable: bool = True) -> 'ConfigurationBuilder':
        """
        Enable or disable hot reload for configuration changes.
        
        Args:
            enable: Whether to enable hot reload
            
        Returns:
            Self for method chaining
        """
        self._hot_reload_enabled = enable
        return self
    
    def build(self) -> PolarisConfiguration:
        """
        Build the final configuration from all sources.
        
        Returns:
            PolarisConfiguration: The built configuration
        """
        # Sort sources by priority (lowest first, so higher priority overwrites)
        sorted_sources = sorted(self.sources, key=lambda s: s.get_priority())
        
        return PolarisConfiguration(
            sources=sorted_sources,
            enable_hot_reload=self._hot_reload_enabled
        )