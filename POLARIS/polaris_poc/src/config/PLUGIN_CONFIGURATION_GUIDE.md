# POLARIS Plugin Configuration Guide

This guide provides comprehensive documentation for creating and maintaining POLARIS plugin configurations. Plugin configurations define how POLARIS integrates with managed systems for monitoring and adaptation.

## Overview

POLARIS plugin configurations follow a standardized YAML format that defines:
- System identification and metadata
- Connection and authentication settings
- Monitoring metrics and collection strategies
- Execution actions and safety constraints
- Documentation and validation guidance

## Configuration Structure

### Required Sections

All plugin configurations must include these sections:

1. **System Identification** (`system_name`, `system_version`)
2. **Implementation** (`implementation`)
3. **Connection** (`connection`)
4. **Monitoring** (`monitoring`)
5. **Execution** (`execution`)
6. **Metadata** (`metadata`)

### Optional Sections

- Custom configuration sections for plugin-specific settings
- Environment variable overrides
- Advanced connector configuration

## Framework Integration

### Configuration Loading

Plugin configurations are loaded by POLARIS adapters during initialization:

1. **MonitorAdapter** loads monitoring configuration
2. **ExecutionAdapter** loads execution configuration
3. **ConfigurationManager** validates against schema
4. Invalid configurations prevent plugin loading

### Schema Validation

All plugin configurations are validated against `managed_system.schema.json`:
- Ensures required fields are present
- Validates data types and formats
- Checks parameter constraints and validation rules
- Provides error messages for configuration issues

### Relationship to Framework Configuration

Plugin configurations integrate with framework configuration (`polaris_config.yaml`):

- **Telemetry Flow**: Plugin metrics flow through framework telemetry subjects
- **Execution Control**: Framework execution subjects carry adaptation commands
- **Logging**: Framework logger settings affect plugin logging
- **NATS Integration**: Framework NATS configuration enables plugin communication

## Configuration Patterns

### Web Service Plugin Pattern

```yaml
system_name: "web_api"
connection:
  protocol: "https"
  host: "${API_HOST}"
  port: 443
  auth:
    type: "token"
    token: "${API_TOKEN}"
monitoring:
  metrics:
    - name: "response_time"
      command: "get_response_time"
      unit: "ms"
      type: "float"
      category: "performance"
    - name: "error_rate"
      command: "get_error_rate"
      unit: "percent"
      type: "float"
      category: "quality"
execution:
  actions:
    - type: "RESTART_SERVICE"
      command: "restart"
      description: "Restart the web service"
      impact:
        severity: "high"
        reversible: false
        estimated_duration: 30.0
```

### Database Plugin Pattern

```yaml
system_name: "database"
connection:
  protocol: "tcp"
  host: "${DB_HOST}"
  port: 5432
  auth:
    type: "basic"
    username: "${DB_USER}"
    password: "${DB_PASSWORD}"
monitoring:
  metrics:
    - name: "active_connections"
      command: "SELECT count(*) FROM pg_stat_activity"
      unit: "count"
      type: "integer"
      category: "resource"
    - name: "query_duration"
      command: "get_avg_query_time"
      unit: "ms"
      type: "float"
      category: "performance"
execution:
  actions:
    - type: "OPTIMIZE_QUERIES"
      command: "ANALYZE"
      description: "Update query statistics"
      impact:
        severity: "low"
        reversible: false
        estimated_duration: 60.0
```

### Container/Kubernetes Plugin Pattern

```yaml
system_name: "k8s_deployment"
connection:
  protocol: "https"
  host: "${K8S_API_SERVER}"
  port: 6443
  auth:
    type: "certificate"
    certificate_path: "${K8S_CERT_PATH}"
monitoring:
  metrics:
    - name: "pod_count"
      command: "kubectl get pods --no-headers | wc -l"
      unit: "count"
      type: "integer"
      category: "resource"
execution:
  actions:
    - type: "SCALE_REPLICAS"
      command: "kubectl scale deployment {name} --replicas={count}"
      parameters:
        - name: "name"
          type: "string"
          required: true
        - name: "count"
          type: "integer"
          required: true
          validation:
            min: 1
            max: 20
```

## Best Practices

### Security

1. **Never store sensitive data in configuration files**
   - Use environment variables for passwords, API keys, tokens
   - Example: `password: "${DB_PASSWORD}"` not `password: "secret123"`

2. **Use secure connection protocols**
   - Prefer HTTPS over HTTP
   - Enable SSL/TLS when available
   - Validate certificates in production

3. **Implement proper authentication**
   - Use strongest available authentication method
   - Rotate credentials regularly
   - Follow principle of least privilege

### Performance

1. **Optimize monitoring intervals**
   - Balance data freshness with system load
   - Consider system dynamics and adaptation requirements
   - Typical range: 1-60 seconds

2. **Configure appropriate timeouts**
   - Account for system response characteristics
   - Allow time for complex operations
   - Prevent indefinite hangs

3. **Use efficient collection strategies**
   - Enable batch collection when supported
   - Use parallel collection for independent metrics
   - Handle errors gracefully

### Reliability

1. **Define meaningful preconditions**
   - Prevent unsafe operations
   - Check system state before actions
   - Provide clear error messages

2. **Set appropriate retry limits**
   - Account for transient failures
   - Avoid infinite retry loops
   - Use exponential backoff when possible

3. **Implement proper error handling**
   - Choose appropriate error handling strategy
   - Log errors for debugging
   - Provide fallback mechanisms

### Documentation

1. **Include comprehensive descriptions**
   - Explain what each metric measures
   - Document action effects and side effects
   - Provide context for configuration choices

2. **Use standard units and naming**
   - Follow established conventions
   - Use descriptive metric names
   - Include units in descriptions

3. **Document relationships and dependencies**
   - Explain metric interdependencies
   - Document action prerequisites
   - Note framework integration points

## Common Configuration Errors

### Schema Validation Errors

1. **Missing Required Fields**
   ```
   Error: 'system_name' is a required property
   Solution: Add system_name field with unique identifier
   ```

2. **Invalid Data Types**
   ```
   Error: 'timeout' should be number, not string
   Solution: Use numeric value: timeout: 30.0 not timeout: "30.0"
   ```

3. **Invalid Parameter Validation**
   ```
   Error: validation.min must be less than validation.max
   Solution: Check parameter validation constraints
   ```

### Runtime Errors

1. **Connection Failures**
   ```
   Error: Cannot connect to host:port
   Solution: Verify system is running and accessible
   ```

2. **Authentication Failures**
   ```
   Error: Authentication failed
   Solution: Check credentials and authentication type
   ```

3. **Command Execution Failures**
   ```
   Error: Command 'get_metric' not found
   Solution: Verify command exists in connector implementation
   ```

### Configuration Logic Errors

1. **Conflicting Preconditions**
   ```
   Error: Action preconditions can never be satisfied
   Solution: Review precondition logic and system state
   ```

2. **Invalid Metric Formulas**
   ```
   Error: Cannot evaluate derived metric formula
   Solution: Check formula syntax and metric name references
   ```

3. **Circular Dependencies**
   ```
   Error: Circular dependency in derived metrics
   Solution: Review metric dependencies and remove cycles
   ```

## Validation Checklist

Before deploying a plugin configuration, verify:

### Required Fields
- [ ] `system_name` is unique and follows naming conventions
- [ ] `system_version` follows semantic versioning
- [ ] `implementation.connector_class` is importable
- [ ] `connection` settings match system requirements
- [ ] `monitoring.enabled` is boolean
- [ ] `execution.enabled` is boolean

### Monitoring Configuration
- [ ] All metrics have valid commands
- [ ] Metric types match expected data
- [ ] Units are standard and consistent
- [ ] Categories are meaningful
- [ ] Derived metric formulas are valid

### Execution Configuration
- [ ] Action commands are valid
- [ ] Parameters have proper validation
- [ ] Preconditions are logical
- [ ] Impact assessments are accurate
- [ ] Constraints prevent conflicts

### Security and Safety
- [ ] No sensitive data in configuration files
- [ ] Environment variables used for credentials
- [ ] Preconditions prevent unsafe operations
- [ ] Timeouts prevent indefinite hangs
- [ ] Error handling is appropriate

### Documentation
- [ ] All sections have clear descriptions
- [ ] Examples are provided where helpful
- [ ] Relationships are documented
- [ ] Common issues are addressed

## Testing Configuration

### Development Testing

1. **Schema Validation**
   ```bash
   # Validate against schema
   polaris config validate --config plugin/config.yaml
   ```

2. **Connection Testing**
   ```bash
   # Test system connectivity
   polaris config test-connection --config plugin/config.yaml
   ```

3. **Metric Collection Testing**
   ```bash
   # Test metric collection
   polaris monitor --config plugin/config.yaml --dry-run
   ```

### Integration Testing

1. **Framework Integration**
   - Load plugin with POLARIS framework
   - Verify metric flow through telemetry subjects
   - Test action execution through execution subjects

2. **World Model Integration**
   - Verify metrics are available to World Models
   - Test action recommendations and execution
   - Validate adaptation loop functionality

3. **Error Handling**
   - Test connection failures
   - Test invalid commands
   - Test precondition violations

## Migration and Updates

### Version Updates

When updating plugin configurations:

1. **Update system_version** following semantic versioning
2. **Maintain backward compatibility** when possible
3. **Document breaking changes** in metadata
4. **Test thoroughly** before deployment

### Schema Changes

When schema changes occur:

1. **Review new requirements** in updated schema
2. **Update configurations** to match new schema
3. **Validate all configurations** against new schema
4. **Update documentation** to reflect changes

### Framework Updates

When POLARIS framework updates:

1. **Review framework changes** affecting plugins
2. **Update configurations** for new features
3. **Test plugin compatibility** with new framework
4. **Update integration documentation**

## Support and Troubleshooting

### Common Issues

1. **Plugin fails to load**
   - Check schema validation errors
   - Verify connector class is importable
   - Review framework logs for details

2. **Metrics not collected**
   - Verify system connectivity
   - Check metric commands in connector
   - Review monitoring configuration

3. **Actions not executed**
   - Check preconditions
   - Verify action commands
   - Review execution constraints

### Getting Help

1. **Framework Documentation**
   - Review POLARIS framework documentation
   - Check API reference for connector interfaces
   - Review example configurations

2. **Community Support**
   - Post questions in POLARIS community forums
   - Share configuration examples
   - Report bugs and feature requests

3. **Professional Support**
   - Contact POLARIS development team
   - Request configuration review
   - Get assistance with complex integrations