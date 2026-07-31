# POLARIS Managed System Plugins

This directory contains plugins for different managed systems that can be monitored and controlled by POLARIS.

## Plugin Architecture

Each managed system plugin consists of:

1. **`config.yaml`** - Declarative configuration defining the system's capabilities
2. **`connector.py`** - Implementation of the communication logic
3. **`__init__.py`** - Makes the directory a Python package

## Plugin Structure

```
extern/                          # Plugin directory
├── __init__.py                  # Package marker
├── config.yaml                  # System configuration
└── connector.py                 # Connector implementation
```

## Configuration Schema

The `config.yaml` file must follow this structure:

### Required Sections

- **`system_name`** - Unique identifier for the managed system
- **`implementation`** - Connector class and settings
- **`connection`** - Connection parameters
- **`monitoring`** - Metrics and collection strategies
- **`execution`** - Available actions and constraints

### Example Configuration

```yaml
system_name: "my_system"
system_version: "1.0.0"

implementation:
  connector_class: "connector.MySystemConnector"
  timeout: 30.0
  max_retries: 3

connection:
  protocol: "tcp"
  host: "localhost"
  port: 8080

monitoring:
  enabled: true
  interval: 5.0
  metrics:
    - name: "cpu_usage"
      command: "get_cpu"
      unit: "percent"
      type: "float"
      description: "CPU utilization percentage"

execution:
  enabled: true
  actions:
    - type: "RESTART"
      command: "restart_service"
      description: "Restart the service"
```

## Connector Implementation

The connector must inherit from `ManagedSystemConnector` and implement these methods:

```python
from polaris.adapters.base import ManagedSystemConnector

class MySystemConnector(ManagedSystemConnector):
    async def connect(self) -> None:
        """Establish connection to the managed system."""
        pass
    
    async def disconnect(self) -> None:
        """Disconnect from the managed system."""
        pass
    
    async def execute_command(self, command_template: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Execute a command on the managed system."""
        pass
    
    async def health_check(self) -> bool:
        """Check if the managed system is healthy."""
        pass
```

## SWIM Plugin Example

The current SWIM plugin demonstrates a complete implementation: ![(based off SWIM TCP interface)](./swim/docs/ExternalControl.pdf)

### Key Features

- **TCP Communication** - Direct socket communication with SWIM
- **Retry Logic** - Exponential backoff for failed commands
- **Rich Metrics** - Server counts, response times, throughput, utilization
- **Derived Metrics** - Calculated metrics like average response time
- **Action Validation** - Precondition checks before execution
- **Parameter Validation** - Type and range validation for action parameters

### Metrics Collected

- `dimmer` - QoS adjustment factor (0.0-1.0)
- `active_servers` - Number of currently active servers
- `max_servers` - Maximum allowed servers
- `servers` - Total server count
- `basic_response_time` - Response time for basic service (ms)
- `optional_response_time` - Response time for optional service (ms)
- `basic_throughput` - Basic service throughput (req/s)
- `optional_throughput` - Optional service throughput (req/s)
- `arrival_rate` - Request arrival rate (req/s)

### Actions Supported

- `ADD_SERVER` - Add a new server to the pool
- `REMOVE_SERVER` - Remove a server from the pool
- `SET_DIMMER` - Adjust QoS by setting dimmer value (0.0-1.0)
- `ADJUST_QOS` - Alias for SET_DIMMER

## Creating a New Plugin

1. **Create Plugin Directory**
   ```bash
   mkdir my_system_plugin
   cd my_system_plugin
   ```

2. **Create Package Marker**
   ```bash
   touch __init__.py
   ```

3. **Define Configuration**
   Create `config.yaml` following the schema (see `managed_system.schema.json`)

4. **Implement Connector**
   Create `connector.py` with your connector class

5. **Test the Plugin**
   ```bash
   python src/scripts/start_component.py monitor --plugin-dir my_system_plugin --validate-only
   ```

## Best Practices

### Configuration
- Use descriptive metric names and units
- Include comprehensive descriptions
- Define proper parameter validation rules
- Set appropriate timeouts and retry limits

### Connector Implementation
- Handle connection failures gracefully
- Implement proper retry logic with backoff
- Log important events and errors
- Validate inputs and handle edge cases
- Use async/await for I/O operations

### Error Handling
- Return meaningful error messages
- Use appropriate exception types
- Log errors with sufficient context
- Implement circuit breaker patterns for unreliable systems

### Performance
- Use connection pooling for HTTP-based systems
- Implement caching where appropriate
- Batch operations when possible
- Monitor and optimize resource usage

## Validation

The framework validates plugin configurations against a JSON schema. Common validation errors:

- **Missing required fields** - Ensure all required sections are present
- **Invalid metric types** - Use supported types: float, integer, boolean, string
- **Invalid action parameters** - Check parameter types and validation rules
- **Malformed connector class path** - Use proper Python import syntax

## Debugging

Use these tools for debugging plugins:

1. **Validation Only**
   ```bash
   python src/scripts/start_component.py monitor --plugin-dir my_plugin --validate-only
   ```

2. **Dry Run**
   ```bash
   python src/scripts/start_component.py monitor --plugin-dir my_plugin --dry-run
   ```

3. **Debug Logging**
   ```bash
   python src/scripts/start_component.py monitor --plugin-dir my_plugin --log-level DEBUG
   ```

4. **NATS Message Monitoring**
   ```bash
   python src/scripts/nats_spy.py --preset telemetry
   ```

## Integration Testing

Test your plugin with the framework:

```python
# Test adapter creation
adapter = MonitorAdapter(
    polaris_config_path="src/config/polaris_config.yaml",
    plugin_dir="my_system_plugin"
)

# Test connector methods
await adapter.connector.health_check()
response = await adapter.connector.execute_command("status")
```

## Support

For questions about plugin development:

1. Check the SWIM plugin as a reference implementation
2. Review the JSON schema for configuration requirements
3. Use the debugging tools to identify issues
4. Check logs for detailed error messages