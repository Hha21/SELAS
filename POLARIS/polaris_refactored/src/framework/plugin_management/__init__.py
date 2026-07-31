"""
Plugin Management System

Provides plugin discovery, loading, and management capabilities.
"""

from .plugin_registry import PolarisPluginRegistry
from .plugin_descriptor import PluginDescriptor
from .plugin_discovery import PluginDiscovery
from .connector_factory import ManagedSystemConnectorFactory

__all__ = [
    'PolarisPluginRegistry',
    'PluginDescriptor',
    'PluginDiscovery',
    'ManagedSystemConnectorFactory'
]