"""
Configuration Sources

Implements various configuration sources for the POLARIS framework.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Union
from abc import ABC, abstractmethod

from ...infrastructure.exceptions import ConfigurationError


class ConfigurationSource(ABC):
    """Base class for configuration sources."""
    
    @abstractmethod
    async def load(self) -> Dict[str, Any]:
        """Load configuration data from this source."""
        pass
    
    @abstractmethod
    def get_priority(self) -> int:
        """Get the priority of this configuration source."""
        pass
    
    @abstractmethod
    def has_changed(self) -> bool:
        """Check if the configuration source has changed."""
        pass


class YAMLConfigurationSource(ConfigurationSource):
    """Configuration source that loads from YAML files."""
    
    def __init__(self, file_path: Union[str, Path], priority: int = 100):
        self.file_path = Path(file_path)
        self._priority = priority
        self._last_modified = None
        self._cached_config = None
    
    async def load(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            if not self.file_path.exists():
                raise ConfigurationError(
                    f"Configuration file not found: {self.file_path}",
                    config_path=str(self.file_path)
                )
            
            with open(self.file_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            
            # Update cache
            self._cached_config = config
            self._last_modified = self.file_path.stat().st_mtime
            
            return config
            
        except yaml.YAMLError as e:
            raise ConfigurationError(
                f"Invalid YAML in configuration file: {self.file_path}",
                config_path=str(self.file_path),
                validation_errors=[str(e)]
            )
        except Exception as e:
            raise ConfigurationError(
                f"Error loading configuration file: {self.file_path}",
                config_path=str(self.file_path),
                validation_errors=[str(e)]
            )
    
    def get_priority(self) -> int:
        """Get the priority of this configuration source."""
        return self._priority
    
    def has_changed(self) -> bool:
        """Check if the YAML file has been modified."""
        if not self.file_path.exists():
            return False
        
        current_modified = self.file_path.stat().st_mtime
        return self._last_modified is None or current_modified != self._last_modified


class EnvironmentConfigurationSource(ConfigurationSource):
    """Configuration source that loads from environment variables."""
    
    def __init__(self, prefix: str = "POLARIS_", priority: int = 200, validate: bool = True):
        self.prefix = prefix
        self._priority = priority
        self.validate = validate
        self._cached_env = None
    
    async def load(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        config = {}
        
        # Get all environment variables with the prefix
        env_vars = {k: v for k, v in os.environ.items() if k.startswith(self.prefix)}
        
        for key, value in env_vars.items():
            # Remove prefix and convert to nested dict
            config_key = key[len(self.prefix):].lower()
            
            # Parse nested keys (e.g., POLARIS_LLM__PROVIDER -> llm.provider)
            keys = config_key.split('__')
            
            # Parse value
            parsed_value = self._parse_value(value, config_key)
            
            # Set nested value in config
            self._set_nested_value(config, keys, parsed_value)
        
        self._cached_env = env_vars.copy()
        return config
    
    def _parse_value(self, value: str, key: str = "") -> Any:
        """Parse environment variable value to appropriate type."""
        # Handle boolean values
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        
        # Handle numeric values
        try:
            if '.' in value:
                return float(value)
            else:
                return int(value)
        except ValueError:
            pass
        
        # Handle list values (comma-separated)
        if ',' in value:
            return self._parse_escaped_list(value)
        
        # Return as string
        return value
    
    def _parse_escaped_list(self, value: str) -> list:
        """Parse comma-separated list with escape handling."""
        items = []
        current_item = ""
        escaped = False
        
        for char in value:
            if escaped:
                current_item += char
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == ',':
                items.append(current_item.strip())
                current_item = ""
            else:
                current_item += char
        
        if current_item:
            items.append(current_item.strip())
        
        return items
    
    def _set_nested_value(self, config: Dict[str, Any], key: str, value: Any) -> None:
        """Set a nested value in the configuration dictionary."""
        keys = key if isinstance(key, list) else [key]
        
        current = config
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = value
    
    def get_priority(self) -> int:
        """Get the priority of this configuration source."""
        return self._priority
    
    def has_changed(self) -> bool:
        """Check if environment variables have changed."""
        current_env = {k: v for k, v in os.environ.items() if k.startswith(self.prefix)}
        return self._cached_env != current_env