"""
Plugin Descriptor

Describes a plugin with its metadata and validation status.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List


@dataclass
class PluginDescriptor:
    """Describes a plugin with its metadata and validation status."""
    
    plugin_id: str
    plugin_type: str
    version: str
    path: Path
    metadata: Dict[str, Any]
    connector_class_name: str
    module_name: str
    last_modified: float
    is_valid: bool = True
    validation_errors: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Post-initialization validation."""
        if not self.plugin_id:
            self.plugin_id = self.path.name
        
        if not self.module_name:
            self.module_name = "connector"
        
        if not self.connector_class_name and self.metadata:
            self.connector_class_name = self.metadata.get('connector_class', '')
    
    @property
    def display_name(self) -> str:
        """Get display name for the plugin."""
        return self.metadata.get('name', self.plugin_id)
    
    @property
    def description(self) -> str:
        """Get description for the plugin."""
        return self.metadata.get('description', f'Plugin {self.plugin_id}')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'plugin_id': self.plugin_id,
            'plugin_type': self.plugin_type,
            'version': self.version,
            'path': str(self.path),
            'metadata': self.metadata,
            'connector_class_name': self.connector_class_name,
            'module_name': self.module_name,
            'last_modified': self.last_modified,
            'is_valid': self.is_valid,
            'validation_errors': self.validation_errors,
            'display_name': self.display_name,
            'description': self.description
        }