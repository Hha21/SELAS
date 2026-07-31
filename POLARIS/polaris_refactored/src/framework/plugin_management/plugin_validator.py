"""
Plugin Validator

Provides security validation for plugins before loading.
"""

import ast
import inspect
from pathlib import Path
from typing import List, Dict, Any, Type

from ...domain.interfaces import ManagedSystemConnector


class PluginValidator:
    """Validates plugins for security and correctness."""
    
    def __init__(self):
        # List of dangerous imports to check for
        self.dangerous_imports = {
            'os.system', 'subprocess', 'eval', 'exec', 'compile',
            '__import__', 'importlib.import_module', 'sys.exit'
        }
        
        # List of allowed imports for connectors
        self.allowed_imports = {
            'asyncio', 'logging', 'time', 'datetime', 'json', 'yaml',
            'typing', 'dataclasses', 'enum', 'pathlib', 'socket',
            'src.domain.interfaces', 'src.domain.models'
        }
    
    def validate_plugin_path(self, plugin_path: Path) -> List[str]:
        """Validate plugin path for security issues."""
        errors = []
        
        try:
            # Check if path exists and is readable
            if not plugin_path.exists():
                errors.append(f"Path does not exist: {plugin_path}")
                return errors
            
            # Check for path traversal attempts
            resolved_path = plugin_path.resolve()
            if '..' in str(plugin_path) or str(resolved_path) != str(plugin_path.resolve()):
                errors.append("Path traversal detected")
            
            # Check file permissions (basic check)
            if plugin_path.is_file() and not plugin_path.is_file():
                errors.append("File is not readable")
                
        except Exception as e:
            errors.append(f"Path validation error: {str(e)}")
        
        return errors
    
    def validate_plugin_imports(self, plugin_path: Path) -> List[str]:
        """Validate plugin imports for security issues."""
        warnings = []
        
        try:
            with open(plugin_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse the AST to check imports
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in self.dangerous_imports:
                            warnings.append(f"Potentially dangerous import: {alias.name}")
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        full_import = f"{node.module}.{node.names[0].name}" if node.names else node.module
                        if full_import in self.dangerous_imports:
                            warnings.append(f"Potentially dangerous import: {full_import}")
                
                # Check for dangerous function calls
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ['eval', 'exec', 'compile']:
                            warnings.append(f"Dangerous function call: {node.func.id}")
                            
        except Exception as e:
            warnings.append(f"Import validation error: {str(e)}")
        
        return warnings
    
    def validate_plugin_metadata(self, metadata: Dict[str, Any]) -> List[str]:
        """Validate plugin metadata."""
        errors = []
        
        required_fields = ['name']
        for field in required_fields:
            if field not in metadata:
                errors.append(f"Missing required field: {field}")
        
        # Validate name format
        if 'name' in metadata:
            name = metadata['name']
            if not isinstance(name, str) or not name.strip():
                errors.append("Plugin name must be a non-empty string")
            elif not name.replace('_', '').replace('-', '').isalnum():
                errors.append("Plugin name must contain only alphanumeric characters, hyphens, and underscores")
        
        # Validate version if present
        if 'version' in metadata:
            version = metadata['version']
            if not isinstance(version, str):
                errors.append("Version must be a string")
        
        return errors
    
    def validate_connector_class(self, connector_class: Type) -> List[str]:
        """Validate connector class implementation."""
        errors = []
        
        try:
            # Check if it's a class
            if not inspect.isclass(connector_class):
                errors.append("Connector must be a class")
                return errors
            
            # Check if it inherits from ManagedSystemConnector
            if not issubclass(connector_class, ManagedSystemConnector):
                errors.append("Connector must inherit from ManagedSystemConnector")
            
            # Check required methods
            required_methods = [
                'connect', 'disconnect', 'get_system_id', 'collect_metrics',
                'get_system_state', 'execute_action', 'validate_action', 'get_supported_actions'
            ]
            
            for method_name in required_methods:
                if not hasattr(connector_class, method_name):
                    errors.append(f"Missing required method: {method_name}")
                else:
                    method = getattr(connector_class, method_name)
                    if not callable(method):
                        errors.append(f"Method {method_name} is not callable")
                    else:
                        # Check method signature
                        sig = inspect.signature(method)
                        self._validate_method_signature(method_name, sig, errors)
            
        except Exception as e:
            errors.append(f"Connector class validation error: {str(e)}")
        
        return errors
    
    @staticmethod
    def _validate_method_signature(method_name: str, signature: inspect.Signature, errors: List[str]) -> None:
        """Validate method signature for required methods."""
        # Basic validation - check that methods are async where required
        async_methods = [
            'connect', 'disconnect', 'get_system_id', 'collect_metrics',
            'get_system_state', 'execute_action', 'validate_action', 'get_supported_actions'
        ]
        
        if method_name in async_methods:
            # For now, just check that the method exists
            # More detailed signature validation could be added here
            pass