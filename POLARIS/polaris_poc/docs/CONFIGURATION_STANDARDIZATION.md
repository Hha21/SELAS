# POLARIS Configuration Standardization

## Overview

This document describes the standardized configuration management approach implemented across the POLARIS framework, ensuring consistent configuration loading, validation, and access patterns.

## Configuration Architecture

### 1. Framework Configuration (`polaris_config.yaml`)

**Location**: `src/config/polaris_config.yaml`
**Purpose**: Core POLARIS framework settings
**Schema**: `src/config/framework_config.schema.json`

**Sections**:
- `nats`: NATS server connection settings
- `telemetry`: Monitor adapter telemetry configuration
- `execution`: Execution adapter configuration  
- `logger`: Framework logging settings
- `digital_twin`: Digital Twin component configuration

### 2. Plugin Configuration (`config.yaml`)

**Location**: `<plugin_dir>/config.yaml`
**Purpose**: Managed system specific settings
**Schema**: `src/config/managed_system.schema.json`

**Sections**:
- `system_name`: System identification
- `implementation`: Connector class and settings
- `connection`: System connection parameters
- `monitoring`: Metrics and collection configuration
- `execution`: Available actions and constraints

### 3. World Model Configuration (`world_model.yaml`)

**Location**: `src/config/world_model.yaml`
**Purpose**: Digital Twin World Model implementations
**Schema**: Validated by `DigitalTwinConfigManager`

**Sections**:
- `mock`: Mock implementation settings
- `gemini`: Gemini LLM configuration
- `statistical`: Statistical model settings
- `hybrid`: Multi-model fusion configuration

## Configuration Managers

### 1. ConfigurationManager (`polaris.common.config`)

**Used by**: Monitor and Execution adapters
**Purpose**: Generic configuration loading with schema validation

**Key Methods**:
- `load_framework_config()`: Load POLARIS framework config
- `load_plugin_config()`: Load and validate plugin config
- `get_monitoring_config()`: Get monitoring settings
- `get_execution_config()`: Get execution settings

### 2. DigitalTwinConfigManager (`polaris.common.digital_twin_config`)

**Used by**: Digital Twin components
**Purpose**: Specialized Digital Twin configuration with environment overrides

**Key Methods**:
- `load_configuration()`: Load complete Digital Twin config
- `get_nats_config()`: Get NATS settings
- `get_grpc_config()`: Get gRPC settings
- `get_active_model_config()`: Get current World Model config
- `create_model_config_summary()`: Generate config summary

## Standardized Configuration Access

### Adapters (Monitor/Execution)

```python
# Initialization
self.config_manager = ConfigurationManager(self.logger)
self.framework_config = self.config_manager.load_framework_config(config_path)
self.plugin_config = self.config_manager.load_plugin_config(plugin_dir, validate=True)

# Access patterns
telemetry_config = self.framework_config.get("telemetry", {})
monitoring_config = self.config_manager.get_monitoring_config()
```

### Digital Twin Agent

```python
# Initialization
self.config_manager = DigitalTwinConfigManager(self.logger)
complete_config = self.config_manager.load_configuration(config_path)

# Access patterns
nats_config = self.config_manager.get_nats_config()
grpc_config = self.config_manager.get_grpc_config()
active_model = self.config_manager.get_active_model_config()
```

## Environment Variable Support

### Framework Configuration
All framework configuration keys are automatically flattened to environment variables:
- `nats.url` → `NATS_URL`
- `telemetry.batch_size` → `TELEMETRY_BATCH_SIZE`
- `digital_twin.grpc.port` → `DIGITAL_TWIN_GRPC_PORT`

### Digital Twin Specific Overrides
- `DIGITAL_TWIN_WORLD_MODEL_IMPLEMENTATION`: Override World Model type
- `DIGITAL_TWIN_GRPC_PORT`: Override gRPC port
- `DIGITAL_TWIN_LOG_LEVEL`: Override log level
- `GEMINI_API_KEY`: Gemini API key (when using Gemini model)

## Configuration Validation

### JSON Schema Validation
- **Framework Config**: Validated against `framework_config.schema.json`
- **Plugin Config**: Validated against `managed_system.schema.json`
- **World Model Config**: Validated by `DigitalTwinConfigManager`

### Runtime Validation
- Port availability checks
- API key presence validation
- Model implementation availability
- Required dependency checks

## Startup Scripts

### Unified Startup Script
**Location**: `src/scripts/start_component.py`
**Usage**:
```bash
# Start Monitor adapter
python src/scripts/start_component.py monitor --plugin-dir extern

# Start Execution adapter  
python src/scripts/start_component.py execution --plugin-dir extern

# Start Digital Twin
python src/scripts/start_component.py digital-twin

# Start Digital Twin with specific World Model
python src/scripts/start_component.py digital-twin --world-model gemini
```

## Configuration File Locations

```
polaris_poc/
├── src/config/
│   ├── polaris_config.yaml          # Framework configuration
│   ├── framework_config.schema.json # Framework validation schema
│   ├── managed_system.schema.json   # Plugin validation schema
│   └── world_model.yaml             # World Model configurations
├── extern/
│   └── config.yaml                  # SWIM plugin configuration
└── logs/
    └── digital_twin.log             # Digital Twin logs (if configured)
```

## Best Practices

### 1. Configuration Loading
- Always use appropriate configuration manager for component type
- Load schema and validate configurations
- Handle configuration errors gracefully
- Log configuration summaries (without sensitive data)

### 2. Configuration Access
- Use getter methods instead of direct dictionary access
- Provide sensible defaults for optional settings
- Cache frequently accessed configuration values
- Use environment variables for runtime overrides

### 3. Configuration Updates
- Update both configuration files and schemas together
- Validate changes against schemas before deployment
- Document new configuration options
- Maintain backward compatibility when possible

### 4. Security
- Never log sensitive configuration values (API keys, passwords)
- Use environment variables for secrets
- Validate configuration values for security implications
- Restrict file permissions on configuration files

## Migration Guide

### From Old Configuration Approach
1. **Replace manual config extraction** with configuration manager methods
2. **Add schema validation** to configuration loading
3. **Use standardized getter methods** instead of direct dictionary access
4. **Update startup scripts** to use unified `start_component.py`

### Example Migration
```python
# Old approach
with open(config_path) as f:
    config = yaml.safe_load(f)
nats_url = config.get("nats", {}).get("url", "nats://localhost:4222")

# New approach  
config_manager = ConfigurationManager(logger)
framework_config = config_manager.load_framework_config(config_path)
nats_url = framework_config.get("nats", {}).get("url", "nats://localhost:4222")
```

## Troubleshooting

### Common Issues
1. **Schema validation errors**: Check configuration against schema files
2. **Missing environment variables**: Verify required env vars are set
3. **Configuration file not found**: Check file paths and permissions
4. **Invalid configuration values**: Validate against schema constraints

### Debug Steps
1. Enable debug logging: `--log-level DEBUG`
2. Use validation mode: `--validate-only`
3. Check configuration summary in logs
4. Verify schema files are present and valid
5. Test with minimal configuration first

## Future Enhancements

### Planned Improvements
- **Configuration hot-reloading**: Runtime configuration updates
- **Configuration versioning**: Support for configuration migrations
- **Configuration templates**: Predefined configuration sets
- **Configuration UI**: Web-based configuration management
- **Configuration encryption**: Encrypted sensitive values