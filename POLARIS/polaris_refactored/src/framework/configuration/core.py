"""
Core Configuration Management

Provides the main configuration class for the POLARIS framework.
"""

import asyncio
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from .sources import ConfigurationSource
from .models import FrameworkConfiguration, ManagedSystemConfiguration
from ...infrastructure.exceptions import ConfigurationError


class PolarisConfiguration:
    """
    Main configuration class for the POLARIS framework.
    
    Manages configuration from multiple sources with priority handling
    and optional hot reload capabilities.
    """
    
    def __init__(self, sources: Optional[List[ConfigurationSource]] = None, enable_hot_reload: bool = False):
        self.sources = sources or []
        self._enable_hot_reload = enable_hot_reload
        self._config_data: Dict[str, Any] = {}
        self._reload_callbacks: List[Callable[[], None]] = []
        self._hot_reload_thread: Optional[threading.Thread] = None
        self._stop_hot_reload = threading.Event()
        
        # Load initial configuration
        asyncio.create_task(self._load_configuration())
        
        if enable_hot_reload:
            self._start_hot_reload_monitoring()
    
    def __del__(self):
        """Cleanup when configuration is destroyed."""
        self.stop_hot_reload()
    
    async def _load_configuration(self) -> None:
        """Load configuration from all sources."""
        try:
            merged_config = {}
            
            # Load from all sources in priority order
            for source in sorted(self.sources, key=lambda s: s.get_priority()):
                try:
                    source_config = await source.load()
                    merged_config = self._deep_merge(merged_config, source_config)
                except Exception as e:
                    # Log error but continue with other sources
                    print(f"Warning: Failed to load configuration from source: {e}")
            
            self._config_data = merged_config
            
        except Exception as e:
            raise ConfigurationError(
                "Failed to load configuration",
                validation_errors=[str(e)]
            )
    
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two configuration dictionaries."""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _start_hot_reload_monitoring(self) -> None:
        """Start hot reload monitoring in a background thread."""
        if self._hot_reload_thread is not None:
            return
        
        self._hot_reload_thread = threading.Thread(
            target=self._hot_reload_worker,
            daemon=True
        )
        self._hot_reload_thread.start()
    
    def _hot_reload_worker(self) -> None:
        """Worker thread for hot reload monitoring."""
        while not self._stop_hot_reload.wait(1.0):  # Check every second
            try:
                # Check if any source has changed
                changed_sources = [s for s in self.sources if s.has_changed()]
                
                if changed_sources:
                    # Reload configuration
                    asyncio.run(self._load_configuration())
                    
                    # Notify callbacks
                    for callback in self._reload_callbacks:
                        try:
                            callback()
                        except Exception as e:
                            print(f"Error in reload callback: {e}")
                            
            except Exception as e:
                print(f"Error in hot reload worker: {e}")
    
    def stop_hot_reload(self) -> None:
        """Stop hot reload monitoring."""
        if self._hot_reload_thread is not None:
            self._stop_hot_reload.set()
            self._hot_reload_thread.join(timeout=5.0)
            self._hot_reload_thread = None
    
    def add_source(self, source: ConfigurationSource) -> None:
        """Add a configuration source."""
        self.sources.append(source)
        asyncio.create_task(self._load_configuration())
    
    def add_reload_callback(self, callback: Callable[[], None]) -> None:
        """Add a callback to be called when configuration is reloaded."""
        self._reload_callbacks.append(callback)
    
    def remove_reload_callback(self, callback: Callable[[], None]) -> None:
        """Remove a reload callback."""
        if callback in self._reload_callbacks:
            self._reload_callbacks.remove(callback)
    
    def reload_configuration(self) -> None:
        """Manually reload configuration."""
        asyncio.create_task(self._load_configuration())
    
    def is_hot_reload_enabled(self) -> bool:
        """Check if hot reload is enabled."""
        return self._enable_hot_reload
    
    def get_raw_config(self) -> Dict[str, Any]:
        """Get the raw configuration dictionary."""
        return self._config_data.copy()
    
    def get_framework_config(self) -> FrameworkConfiguration:
        """Get the framework configuration."""
        framework_data = self._config_data.get("framework", {})
        
        # Create FrameworkConfiguration with validation
        try:
            return FrameworkConfiguration(**framework_data)
        except Exception as e:
            # Return default configuration if validation fails
            print(f"Warning: Invalid framework configuration, using defaults: {e}")
            return FrameworkConfiguration()
    
    def get_managed_system_config(self, system_id: str) -> Optional[ManagedSystemConfiguration]:
        """Get configuration for a specific managed system."""
        managed_systems = self._config_data.get("managed_systems", {})
        
        if system_id not in managed_systems:
            return None
        
        system_data = managed_systems[system_id]
        system_data["system_id"] = system_id  # Ensure system_id is set
        
        try:
            return ManagedSystemConfiguration(**system_data)
        except Exception as e:
            print(f"Warning: Invalid configuration for system {system_id}: {e}")
            return None
    
    def get_all_managed_systems(self) -> Dict[str, ManagedSystemConfiguration]:
        """Get all managed system configurations."""
        managed_systems = self._config_data.get("managed_systems", {})
        result = {}
        
        for system_id, system_data in managed_systems.items():
            config = self.get_managed_system_config(system_id)
            if config:
                result[system_id] = config
        
        return result
    
    async def wait_for_load(self) -> None:
        """Wait until the configuration is loaded."""
        while not self._config_data:
            await asyncio.sleep(0.1)