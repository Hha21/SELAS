"""
Configuration Validation System for POLARIS.

This module provides comprehensive configuration validation with contextual error messages,
actionable suggestions, and comprehensive error reporting for the POLARIS framework.
"""

import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Tuple

try:
    from jsonschema import validate, ValidationError, Draft7Validator
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    ValidationError = Exception
    Draft7Validator = None

import yaml

from .validation_result import (
    ValidationResult, ValidationIssue, ValidationContext, ValidationSeverity, 
    ValidationCategory, MultiFileValidationResult
)
from .error_suggestions import ConfigurationErrorSuggestionDatabase


class ConfigurationValidator:
    """
    Configuration validator with contextual error messages and suggestions.
    
    This validator provides comprehensive JSON schema validation with:
    - Contextual error messages with full configuration paths
    - Actionable suggestions for common configuration mistakes
    - Error classification system for different types of validation failures
    - Support for multiple validation contexts (framework, world model, plugin)
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize the configuration validator.
        
        Args:
            logger: Logger instance for structured logging
        """
        self.logger = logger or logging.getLogger(__name__)
        self._suggestion_db = ConfigurationErrorSuggestionDatabase()
        self._performance_thresholds = self._build_performance_thresholds()
        
        if not JSONSCHEMA_AVAILABLE:
            raise ImportError(
                "jsonschema is required for configuration validation. "
                "Install with: pip install jsonschema"
            )
    
    def _get_default_schema_path(self, config_type: str) -> Optional[Path]:
        """Get default schema path based on configuration type."""
        schema_path = Path(__file__).parent.parent / "config" / f"{config_type}_config.schema.json"
        return schema_path if schema_path.exists() else None

    def validate_config_file(
        self,
        config_path: Union[str, Path],
        schema_path: Optional[Union[str, Path]] = None,
        config_type: str = "unknown"
    ) -> ValidationResult:
        """Validate a configuration file with comprehensive error reporting.
        
        Args:
            config_path: Path to configuration file to validate
            schema_path: Path to JSON schema file (optional)
            config_type: Type of configuration for context-specific validation
            
        Returns:
            ValidationResult with comprehensive validation information
        """
        config_path = Path(config_path)
        
        # Create validation context
        context = ValidationContext(
            config_type=config_type,
            config_path=str(config_path),
            schema_path=str(schema_path) if schema_path else ""
        )
        
        result = ValidationResult(valid=True, context=context)
        
        # Check if file exists
        if not config_path.exists():
            result.add_issue(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.SYNTAX,
                message=f"Configuration file not found: {config_path}",
                config_path=str(config_path),
                suggestions=[
                    "Check if the file path is correct",
                    "Ensure the file exists and is readable",
                    "Verify file permissions allow reading"
                ]
            ))
            return result
        
        # Load configuration
        try:
            config = self._load_config_file(config_path)
        except Exception as e:
            result.add_issue(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.SYNTAX,
                message=f"Failed to parse configuration file: {str(e)}",
                config_path=str(config_path),
                suggestions=self._get_parsing_suggestions(config_path, str(e))
            ))
            return result
        
        # Schema validation (with auto-discovery if schema_path not supplied)
        resolved_schema_path = schema_path
        if not resolved_schema_path:
            resolved_schema_path = self._get_default_schema_path(config_type)

        if resolved_schema_path:
            schema_result = self._validate_against_schema(config, resolved_schema_path, str(config_path))
            result.add_issues(schema_result.issues)
        
        # Context-specific validation
        context_result = self._validate_config_context(config, config_type, str(config_path))
        result.add_issues(context_result.issues)
        
        # Performance analysis
        performance_result = self._analyze_performance_implications(config, config_type, str(config_path))
        result.add_issues(performance_result.issues)
        
        # Security analysis
        security_result = self._analyze_security_implications(config, config_type, str(config_path))
        result.add_issues(security_result.issues)
        
        return result
    
    def validate_config_dict(
        self,
        config: Dict[str, Any],
        schema: Optional[Dict[str, Any]] = None,
        config_type: str = "unknown",
        config_path: str = ""
    ) -> ValidationResult:
        """Validate a configuration dictionary with comprehensive error reporting.
        
        Args:
            config: Configuration dictionary to validate
            schema: JSON schema dictionary (optional)
            config_type: Type of configuration for context-specific validation
            config_path: Path context for error reporting
            
        Returns:
            ValidationResult with comprehensive validation information
        """
        # Create validation context
        context = ValidationContext(
            config_type=config_type,
            config_path=config_path
        )
        
        result = ValidationResult(valid=True, context=context)
        
        # Schema validation
        if schema:
            schema_result = self._validate_dict_against_schema(config, schema, config_path)
            result.add_issues(schema_result.issues)
        
        # Context-specific validation
        context_result = self._validate_config_context(config, config_type, config_path)
        result.add_issues(context_result.issues)
        
        # Performance analysis
        performance_result = self._analyze_performance_implications(config, config_type, config_path)
        result.add_issues(performance_result.issues)
        
        # Security analysis
        security_result = self._analyze_security_implications(config, config_type, config_path)
        result.add_issues(security_result.issues)
        
        return result
    
    def _load_config_file(self, config_path: Path) -> Dict[str, Any]:
        """Load configuration file based on extension."""
        if config_path.suffix in ['.yaml', '.yml']:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        elif config_path.suffix == '.json':
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            raise ValueError(f"Unsupported configuration file type: {config_path.suffix}")
    
    def _validate_against_schema(
        self,
        config: Dict[str, Any],
        schema_path: Union[str, Path],
        config_path: str
    ) -> ValidationResult:
        """Validate configuration against JSON schema."""
        result = ValidationResult(valid=True)
        
        try:
            # Load schema
            schema_path = Path(schema_path)
            if not schema_path.exists():
                result.add_issue(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.SCHEMA,
                    message=f"Schema file not found: {schema_path}",
                    config_path=config_path,
                    suggestions=["Schema validation will be skipped"]
                ))
                return result
            
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = json.load(f)
            
            return self._validate_dict_against_schema(config, schema, config_path)
            
        except Exception as e:
            result.add_issue(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                category=ValidationCategory.SCHEMA,
                message=f"Failed to load or validate schema: {str(e)}",
                config_path=config_path,
                suggestions=["Schema validation will be skipped", "Check schema file format and accessibility"]
            ))
            return result
    
    def _validate_dict_against_schema(
        self,
        config: Dict[str, Any],
        schema: Dict[str, Any],
        config_path: str
    ) -> ValidationResult:
        """Validate configuration dictionary against schema."""
        result = ValidationResult(valid=True)
        
        try:
            # Use Draft7Validator for better error reporting
            validator = Draft7Validator(schema)
            errors = sorted(validator.iter_errors(config), key=lambda e: e.path)
            
            for error in errors:
                field_path = ".".join(str(p) for p in error.absolute_path)
                
                # Create enhanced error message
                issue = self._create_schema_validation_issue(error, field_path, config_path)
                result.add_issue(issue)
            
            if not errors:
                # Add optimization suggestions for valid configurations
                optimization_issues = self._get_optimization_suggestions(config, config_path)
                result.add_issues(optimization_issues)
            
        except Exception as e:
            result.add_issue(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category=ValidationCategory.SCHEMA,
                message=f"Schema validation failed: {str(e)}",
                config_path=config_path,
                suggestions=["Check configuration format and schema compatibility"]
            ))
        
        return result
    
    def _create_schema_validation_issue(
        self,
        error: ValidationError,
        field_path: str,
        config_path: str
    ) -> ValidationIssue:
        """Create a validation issue from a schema validation error."""
        # Build contextual error message
        base_message = f"Schema validation failed: {error.message}"
        
        # Get context-specific suggestions
        suggestions = self._get_error_suggestions(field_path, error.message, error.validator)
        
        # Get examples of correct configuration
        examples = self._get_configuration_examples(field_path, error.validator_value)
        
        return ValidationIssue(
            severity=ValidationSeverity.ERROR,
            category=ValidationCategory.SCHEMA,
            message=base_message,
            config_path=config_path,
            field_path=field_path,
            suggestions=suggestions,
            examples=examples
        )
    
    def _validate_config_context(
        self,
        config: Dict[str, Any],
        config_type: str,
        config_path: str
    ) -> ValidationResult:
        """Perform context-specific validation based on configuration type."""
        result = ValidationResult(valid=True)
        
        if config_type == "framework":
            result.issues.extend(self._validate_framework_config(config, config_path))
        elif config_type == "world_model":
            result.issues.extend(self._validate_world_model_config(config, config_path))
        elif config_type == "plugin":
            result.issues.extend(self._validate_plugin_config(config, config_path))
        
        return result
    
    def _validate_framework_config(self, config: Dict[str, Any], config_path: str) -> List[ValidationIssue]:
        """Validate framework-specific configuration rules."""
        issues = []
        
        # Validate NATS URL format and accessibility
        if "nats" in config and "url" in config["nats"]:
            nats_url = config["nats"]["url"]
            if not nats_url.startswith("nats://"):
                suggestions, examples = self._suggestion_db.get_suggestions_for_error(
                    field_path="nats.url",
                    error_message="NATS URL must start with 'nats://'",
                    error_type="pattern_mismatch",
                    config_type="framework",
                    current_value=nats_url
                )
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.SCHEMA,
                    message="NATS URL must start with 'nats://'",
                    config_path=config_path,
                    field_path="nats.url",
                    suggestions=suggestions,
                    examples=examples
                ))
        
        # Validate Digital Twin gRPC port
        if "digital_twin" in config and "grpc" in config["digital_twin"]:
            grpc_config = config["digital_twin"]["grpc"]
            if "port" in grpc_config:
                port = grpc_config["port"]
                if not isinstance(port, int) or port < 1 or port > 65535:
                    suggestions, examples = self._suggestion_db.get_suggestions_for_error(
                        field_path="digital_twin.grpc.port",
                        error_message=f"Invalid gRPC port: {port}",
                        error_type="out_of_range",
                        config_type="framework",
                        current_value=port
                    )
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.SCHEMA,
                        message=f"Invalid gRPC port: {port}",
                        config_path=config_path,
                        field_path="digital_twin.grpc.port",
                        suggestions=suggestions,
                        examples=examples
                    ))
        
        # Validate World Model implementation
        if "digital_twin" in config and "world_model" in config["digital_twin"]:
            wm_config = config["digital_twin"]["world_model"]
            if "implementation" in wm_config:
                impl = wm_config["implementation"]
                valid_implementations = ["mock", "gemini", "statistical", "hybrid"]
                if impl not in valid_implementations:
                    suggestions, examples = self._suggestion_db.get_suggestions_for_error(
                        field_path="digital_twin.world_model.implementation",
                        error_message=f"Unknown World Model implementation: {impl}",
                        error_type="invalid_enum",
                        config_type="framework",
                        current_value=impl
                    )
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        category=ValidationCategory.COMPATIBILITY,
                        message=f"Unknown World Model implementation: {impl}",
                        config_path=config_path,
                        field_path="digital_twin.world_model.implementation",
                        suggestions=suggestions,
                        examples=examples
                    ))
        
        return issues
    
    def _validate_world_model_config(self, config: Dict[str, Any], config_path: str) -> List[ValidationIssue]:
        """Validate world model-specific configuration rules."""
        issues = []

        # World model YAMLs use a common shape:
        # implementation: <impl>
        # config: { ... }
        implementation = config.get("implementation")
        cfg = config.get("config", {}) if isinstance(config.get("config"), dict) else {}

        # Validate Gemini configuration when selected
        if implementation == "gemini":
            # Check API key environment variable
            if "api_key_env" in cfg:
                api_key_env = cfg["api_key_env"]
                if not isinstance(api_key_env, str) or not api_key_env:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.SCHEMA,
                        message="api_key_env must be a non-empty string",
                        config_path=config_path,
                        field_path="config.api_key_env",
                        suggestions=["Set config.api_key_env to the env var name holding your API key (e.g., GEMINI_API_KEY)"]
                    ))
                elif api_key_env not in os.environ:
                    suggestions, _ = self._suggestion_db.get_suggestions_for_error(
                        field_path="config.api_key_env",
                        error_message=f"Gemini API key environment variable not set: {api_key_env}",
                        error_type="missing_env_var",
                        config_type="world_model",
                        current_value=api_key_env
                    )
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.DEPENDENCY,
                        message=f"Gemini API key environment variable not set: {api_key_env}",
                        config_path=config_path,
                        field_path="config.api_key_env",
                        suggestions=suggestions or [f"Export {api_key_env} in your environment before starting POLARIS"]
                    ))

            # Validate temperature range if provided
            if "temperature" in cfg:
                temp = cfg["temperature"]
                if not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
                    suggestions, examples = self._suggestion_db.get_suggestions_for_error(
                        field_path="config.temperature",
                        error_message=f"Invalid temperature value: {temp}",
                        error_type="out_of_range",
                        config_type="world_model",
                        current_value=temp
                    )
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.SCHEMA,
                        message=f"Invalid temperature value: {temp}",
                        config_path=config_path,
                        field_path="config.temperature",
                        suggestions=suggestions,
                        examples=examples
                    ))

        # Validate statistical configuration when selected
        if implementation == "statistical":
            ts = cfg.get("time_series", {}) if isinstance(cfg.get("time_series"), dict) else {}
            if "window_size" in ts:
                window_size = ts["window_size"]
                if not isinstance(window_size, int) or window_size < 10:
                    perf_suggestions = self._suggestion_db.get_performance_suggestions(
                        "config.time_series.window_size", window_size
                    )
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        category=ValidationCategory.PERFORMANCE,
                        message=f"Window size too small: {window_size}",
                        config_path=config_path,
                        field_path="config.time_series.window_size",
                        suggestions=perf_suggestions or [
                            "Minimum recommended window size: 10",
                            "For stable patterns: 100-1000",
                            "Larger windows = more stable but slower"
                        ]
                    ))

        # Optional: sanity checks for hybrid configuration
        if implementation == "hybrid":
            model_weights = cfg.get("model_weights", {})
            if isinstance(model_weights, dict) and model_weights:
                total = sum(v for v in model_weights.values() if isinstance(v, (int, float)))
                if abs(total - 1.0) > 1e-6:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.INFO,
                        category=ValidationCategory.SCHEMA,
                        message=f"model_weights should sum to 1.0 (current: {total:.3f})",
                        config_path=config_path,
                        field_path="config.model_weights",
                        suggestions=["Normalize weights so they add up to 1.0"]
                    ))

        return issues
    
    def _validate_plugin_config(self, config: Dict[str, Any], config_path: str) -> List[ValidationIssue]:
        """Validate plugin-specific configuration rules."""
        issues = []
        
        # Validate system name format
        if "system_name" in config:
            system_name = config["system_name"]
            if not isinstance(system_name, str) or not system_name.replace("_", "").replace("-", "").isalnum():
                suggestions, examples = self._suggestion_db.get_suggestions_for_error(
                    field_path="system_name",
                    error_message=f"Invalid system name format: {system_name}",
                    error_type="pattern_mismatch",
                    config_type="plugin",
                    current_value=system_name
                )
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.SCHEMA,
                    message=f"Invalid system name format: {system_name}",
                    config_path=config_path,
                    field_path="system_name",
                    suggestions=suggestions,
                    examples=examples
                ))
        
        # Validate connector class format
        if "implementation" in config and "connector_class" in config["implementation"]:
            connector_class = config["implementation"]["connector_class"]
            if not self._is_valid_python_import_path(connector_class):
                suggestions, examples = self._suggestion_db.get_suggestions_for_error(
                    field_path="implementation.connector_class",
                    error_message=f"Invalid connector class format: {connector_class}",
                    error_type="pattern_mismatch",
                    config_type="plugin",
                    current_value=connector_class
                )
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.SCHEMA,
                    message=f"Invalid connector class format: {connector_class}",
                    config_path=config_path,
                    field_path="implementation.connector_class",
                    suggestions=suggestions,
                    examples=examples
                ))
        
        return issues
    
    def _analyze_performance_implications(
        self,
        config: Dict[str, Any],
        config_type: str,
        config_path: str
    ) -> ValidationResult:
        """Analyze configuration for performance implications."""
        result = ValidationResult(valid=True)
        
        # Check telemetry batch sizes
        if "telemetry" in config:
            telemetry = config["telemetry"]
            
            if "batch_size" in telemetry:
                batch_size = telemetry["batch_size"]
                if isinstance(batch_size, int):
                    if batch_size > 1000:
                        result.add_issue(ValidationIssue(
                            severity=ValidationSeverity.WARNING,
                            category=ValidationCategory.PERFORMANCE,
                            message=f"Large batch size may cause memory issues: {batch_size}",
                            config_path=config_path,
                            field_path="telemetry.batch_size",
                            suggestions=[
                                "Consider reducing batch size to 100-500",
                                "Monitor memory usage with large batches",
                                "Balance throughput vs memory consumption"
                            ]
                        ))
                    elif batch_size < 10:
                        result.add_issue(ValidationIssue(
                            severity=ValidationSeverity.INFO,
                            category=ValidationCategory.PERFORMANCE,
                            message=f"Small batch size may reduce efficiency: {batch_size}",
                            config_path=config_path,
                            field_path="telemetry.batch_size",
                            suggestions=[
                                "Consider increasing batch size to 50-100",
                                "Small batches increase NATS message overhead",
                                "Good for development, less efficient for production"
                            ]
                        ))
        
        # Check concurrent query limits
        if "digital_twin" in config and "performance" in config["digital_twin"]:
            perf_config = config["digital_twin"]["performance"]
            
            if "max_concurrent_queries" in perf_config:
                max_concurrent = perf_config["max_concurrent_queries"]
                if isinstance(max_concurrent, int) and max_concurrent > 50:
                    result.add_issue(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        category=ValidationCategory.PERFORMANCE,
                        message=f"High concurrent query limit may overwhelm World Model: {max_concurrent}",
                        config_path=config_path,
                        field_path="digital_twin.performance.max_concurrent_queries",
                        suggestions=[
                            "Consider API rate limits for external models",
                            "Monitor World Model response times",
                            "Start with lower values and increase gradually"
                        ]
                    ))
        
        return result
    
    def _analyze_security_implications(
        self,
        config: Dict[str, Any],
        config_type: str,
        config_path: str
    ) -> ValidationResult:
        """Analyze configuration for security implications."""
        result = ValidationResult(valid=True)
        
        # Check for insecure NATS URLs
        if "nats" in config and "url" in config["nats"]:
            nats_url = config["nats"]["url"]
            if "localhost" in nats_url or "127.0.0.1" in nats_url:
                result.add_issue(ValidationIssue(
                    severity=ValidationSeverity.INFO,
                    category=ValidationCategory.SECURITY,
                    message="NATS URL uses localhost - ensure this is intended for development",
                    config_path=config_path,
                    field_path="nats.url",
                    suggestions=[
                        "Use specific hostnames in production",
                        "Consider TLS encryption: tls://hostname:port",
                        "Implement NATS authentication for production"
                    ]
                ))
        
        # Check for insecure gRPC binding
        if "digital_twin" in config and "grpc" in config["digital_twin"]:
            grpc_config = config["digital_twin"]["grpc"]
            if "host" in grpc_config and grpc_config["host"] == "0.0.0.0":
                result.add_issue(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.SECURITY,
                    message="gRPC server bound to all interfaces (0.0.0.0)",
                    config_path=config_path,
                    field_path="digital_twin.grpc.host",
                    suggestions=[
                        "Bind to specific interface in production",
                        "Use 127.0.0.1 for local-only access",
                        "Implement proper authentication and TLS"
                    ]
                ))
        
        # Check for debug logging in production-like configs
        if "logger" in config and config["logger"].get("level") == "DEBUG":
            result.add_issue(ValidationIssue(
                severity=ValidationSeverity.INFO,
                category=ValidationCategory.SECURITY,
                message="Debug logging enabled - may expose sensitive information",
                config_path=config_path,
                field_path="logger.level",
                suggestions=[
                    "Use INFO or WARNING level in production",
                    "Debug logging can impact performance",
                    "May log sensitive configuration data"
                ]
            ))
        
        return result
    
    def _get_error_suggestions(self, field_path: str, error_message: str, validator: str) -> List[str]:
        """Get context-aware suggestions for validation errors."""
        error_type = self._classify_validation_error(error_message, validator)
        suggestions, _ = self._suggestion_db.get_suggestions_for_error(
            field_path=field_path,
            error_message=error_message,
            error_type=error_type,
            config_type="unknown"  # Will be enhanced with context in future
        )
        
        return suggestions or ["Check the configuration documentation for this field"]
    
    def _get_configuration_examples(self, field_path: str, validator_value: Any) -> List[str]:
        """Get examples of correct configuration for a field."""
        error_type = "example"  # Generic type for examples
        _, examples = self._suggestion_db.get_suggestions_for_error(
            field_path=field_path,
            error_message="",
            error_type=error_type
        )
        
        # Generate examples from validator value if it's an enum and we don't have specific examples
        if not examples and isinstance(validator_value, list):
            examples.extend([str(v) for v in validator_value[:3]])  # Show first 3 options
        
        return examples
    
    def _get_optimization_suggestions(self, config: Dict[str, Any], config_path: str) -> List[ValidationIssue]:
        """Get optimization suggestions for valid configurations."""
        suggestions = []
        
        # Suggest performance optimizations
        if "telemetry" in config:
            telemetry = config["telemetry"]
            if telemetry.get("stream", True) and telemetry.get("batch_size", 100) > 50:
                suggestions.append(ValidationIssue(
                    severity=ValidationSeverity.INFO,
                    category=ValidationCategory.PERFORMANCE,
                    message="Consider disabling streaming for high-volume production",
                    config_path=config_path,
                    field_path="telemetry.stream",
                    suggestions=[
                        "Set stream: false for batch-only mode",
                        "Reduces NATS message overhead",
                        "Better for high-volume telemetry"
                    ]
                ))
        
        return suggestions
    
    def _get_parsing_suggestions(self, config_path: Path, error_message: str) -> List[str]:
        """Get suggestions for configuration file parsing errors."""
        suggestions = []
        
        if "yaml" in error_message.lower() or config_path.suffix in ['.yaml', '.yml']:
            suggestions.extend([
                "Check YAML syntax - ensure proper indentation",
                "Verify all quotes are properly closed",
                "Check for tabs vs spaces (use spaces only)",
                "Validate YAML syntax with an online validator"
            ])
        elif "json" in error_message.lower() or config_path.suffix == '.json':
            suggestions.extend([
                "Check JSON syntax - ensure all brackets and braces are closed",
                "Verify all strings are properly quoted",
                "Remove trailing commas",
                "Validate JSON syntax with an online validator"
            ])
        
        suggestions.append("Check file encoding (should be UTF-8)")
        return suggestions
    
    def _classify_validation_error(self, error_message: str, validator: str) -> str:
        """Classify validation error for suggestion lookup."""
        error_message_lower = error_message.lower()
        
        if "required" in error_message_lower:
            return "missing_required"
        elif "pattern" in error_message_lower or validator == "pattern":
            return "pattern_mismatch"
        elif "type" in error_message_lower or validator == "type":
            return "type_mismatch"
        elif "minimum" in error_message_lower or "maximum" in error_message_lower:
            return "out_of_range"
        elif "enum" in error_message_lower or validator == "enum":
            return "invalid_enum"
        else:
            return "default"
    
    def _is_valid_python_import_path(self, path: str) -> bool:
        """Check if a string is a valid Python import path."""
        if not path or not isinstance(path, str):
            return False
        
        parts = path.split('.')
        for part in parts:
            if not part.isidentifier():
                return False
        
        return True
    
    def _build_performance_thresholds(self) -> Dict[str, Dict[str, Any]]:
        """Build performance threshold configurations."""
        return {
            "telemetry.batch_size": {
                "warning_high": 1000,
                "info_low": 10
            },
            "digital_twin.performance.max_concurrent_queries": {
                "warning_high": 50
            },
            "telemetry.queue_maxsize": {
                "warning_high": 10000,
                "info_low": 100
            }
        }
    
    def validate_multiple_files(
        self,
        file_configs: List[Dict[str, Union[str, Path]]],
        stop_on_first_error: bool = False
    ) -> MultiFileValidationResult:
        """Validate multiple configuration files.
        
        Args:
            file_configs: List of dictionaries with 'path', 'schema_path', and 'config_type'
            stop_on_first_error: Whether to stop validation on first error
            
        Returns:
            MultiFileValidationResult with results for all files
        """
        multi_result = MultiFileValidationResult()
        
        for file_config in file_configs:
            config_path = file_config['path']
            schema_path = file_config.get('schema_path')
            config_type = file_config.get('config_type', 'unknown')
            
            try:
                result = self.validate_config_file(config_path, schema_path, config_type)
                multi_result.add_file_result(str(config_path), result)
                
                if stop_on_first_error and not result.valid:
                    self.logger.info(f"Stopping validation on first error in {config_path}")
                    break
                    
            except Exception as e:
                # Create error result for files that couldn't be processed
                error_result = ValidationResult(valid=False)
                error_result.add_issue(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.SYNTAX,
                    message=f"Failed to validate file: {str(e)}",
                    config_path=str(config_path),
                    suggestions=[
                        "Check if file exists and is readable",
                        "Verify file format and syntax",
                        "Check file permissions"
                    ]
                ))
                multi_result.add_file_result(str(config_path), error_result)
                
                if stop_on_first_error:
                    break
        
        return multi_result
    
    def discover_and_validate_configs(
        self,
        search_directory: Union[str, Path],
        config_patterns: Optional[Dict[str, str]] = None
    ) -> MultiFileValidationResult:
        """Discover and validate configuration files in a directory.
        
        Args:
            search_directory: Directory to search for configuration files
            config_patterns: Mapping of file patterns to config types
            
        Returns:
            MultiFileValidationResult with results for discovered files
        """
        search_directory = Path(search_directory)
        
        if config_patterns is None:
            config_patterns = {
                "**/polaris_config.yaml": "framework",
                "**/world_model.yaml": "world_model",
                "**/config.yaml": "plugin",
                "**/*_config.yaml": "plugin"
            }
        
        file_configs = []
        
        for pattern, config_type in config_patterns.items():
            for config_path in search_directory.glob(pattern):
                if config_path.is_file():
                    # Try to find corresponding schema
                    schema_path = self._find_schema_for_config(config_path, config_type)
                    
                    file_configs.append({
                        'path': config_path,
                        'schema_path': schema_path,
                        'config_type': config_type
                    })
        
        self.logger.info(f"Discovered {len(file_configs)} configuration files in {search_directory}")
        return self.validate_multiple_files(file_configs)
    
    def _find_schema_for_config(self, config_path: Path, config_type: str) -> Optional[Path]:
        """Find the appropriate schema file for a configuration file.
        
        Args:
            config_path: Path to configuration file
            config_type: Type of configuration
            
        Returns:
            Path to schema file if found, None otherwise
        """
        # Look for schema files in common locations
        schema_search_paths = [
            config_path.parent,  # Same directory as config
            config_path.parent / "schemas",  # schemas subdirectory
            config_path.parent.parent / "schemas",  # parent schemas directory
        ]
        
        # Schema file naming patterns
        schema_patterns = {
            "framework": ["framework_config.schema.json", "polaris_config.schema.json"],
            "world_model": ["world_model.schema.json", "world_model_config.schema.json"],
            "plugin": ["managed_system.schema.json", "plugin_config.schema.json", "plugin.schema.json"]
        }
        
        patterns = schema_patterns.get(config_type, [f"{config_type}.schema.json"])
        
        for search_path in schema_search_paths:
            if not search_path.exists():
                continue
                
            for pattern in patterns:
                schema_path = search_path / pattern
                if schema_path.exists():
                    return schema_path
        
        return None