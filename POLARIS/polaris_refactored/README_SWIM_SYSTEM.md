# POLARIS SWIM System Setup

This document provides instructions for running the complete POLARIS adaptation system with SWIM, featuring threshold-based reactive strategies and proactive LLM reasoning using Google AI.

## System Overview

The system includes:
- **SWIM Connector**: TCP-based connector for the SWIM exemplar system
- **Threshold Reactive Strategy**: Rule-based adaptation using configurable thresholds
- **LLM Reasoning Strategy**: Intelligent reasoning using Google AI (Gemini)
- **LLM World Model**: Natural language system behavior understanding
- **Complete Observability**: Logging, metrics, and tracing

## Prerequisites

### 1. SWIM System
You need SWIM running on `localhost:4242`. If you don't have SWIM:
- Download from: https://github.com/cps-sei/swim
- Follow SWIM installation instructions
- Start SWIM server on port 4242

### 2. Google AI API Key
Get your API key from: https://makersuite.google.com/app/apikey

### 3. Python Dependencies
```bash
pip install pydantic asyncio dataclasses typing datetime pathlib logging json pyyaml
```

## Quick Start

### 1. Environment Setup
```bash
# Set your Google AI API key
export GOOGLE_AI_API_KEY='your-api-key-here'

# Run environment setup
python setup_environment.py
```

### 2. Start the System
```bash
# Start POLARIS with SWIM
python run_swim_system.py
```

### 3. Alternative: Mock LLM for Testing
If you don't have a Google AI API key, you can run with mock LLM:
```bash
export POLARIS_LLM__PROVIDER=mock
python run_swim_system.py
```

## Configuration

The main configuration is in `config/swim_system_config.yaml`. Key sections:

### SWIM Connection
```yaml
managed_systems:
  swim:
    connection:
      host: "localhost"
      port: 4242
    implementation:
      timeout: 30.0
      max_retries: 3
```

### LLM Configuration (Google AI)
```yaml
llm:
  provider: "google"
  api_endpoint: "https://generativelanguage.googleapis.com"
  api_key: "${GOOGLE_AI_API_KEY}"
  model_name: "gemini-1.5-pro"
  max_tokens: 2000
  temperature: 0.1
```

### Threshold Rules
```yaml
control_reasoning:
  threshold_reactive:
    rules:
      - rule_id: "high_utilization_scale_up"
        conditions:
          - metric_name: "server_utilization"
            operator: "gt"
            value: 0.8
        action_type: "ADD_SERVER"
        priority: 3
```

## System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   SWIM System   │◄──►│ POLARIS Framework │◄──►│  Google AI API  │
│  (localhost:    │    │                  │    │   (Gemini)      │
│   4242)         │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   Adaptation     │
                    │   Strategies:    │
                    │ • Threshold      │
                    │ • LLM Reasoning  │
                    │ • World Model    │
                    └──────────────────┘
```

## Key Components

### 1. SWIM Connector (`plugins/swim/connector.py`)
- Handles TCP communication with SWIM
- Collects metrics: server_count, utilization, response_time, dimmer
- Executes actions: ADD_SERVER, REMOVE_SERVER, SET_DIMMER

### 2. Threshold Reactive Strategy
- Rule-based adaptation using configurable thresholds
- Multi-metric evaluation with logical operators
- Action prioritization and cooldown management
- Fallback to simple reactive behavior

### 3. LLM Reasoning Strategy
- Uses Google AI for intelligent system analysis
- Dynamic tool usage for context gathering
- Multi-turn conversations for complex reasoning
- Confidence-based decision making

### 4. LLM World Model
- Natural language system state representation
- Behavior prediction using LLM forecasting
- Adaptation impact simulation
- Conversation history for context continuity

## Monitoring and Observability

### Logs
- Console output with structured logging
- File logging to `./logs/polaris.log`
- Component-specific loggers

### Metrics
- System metrics (server count, utilization, response time)
- Adaptation metrics (actions executed, success rate)
- LLM metrics (API calls, token usage, confidence scores)

### Tracing
- Distributed tracing for adaptation flows
- LLM operation tracing
- Performance monitoring

## Adaptation Scenarios

### 1. High Server Utilization
```
Trigger: server_utilization > 0.8
Action: ADD_SERVER
Strategy: Threshold Reactive
```

### 2. Low Server Utilization
```
Trigger: server_utilization < 0.3
Action: REMOVE_SERVER
Strategy: Threshold Reactive
```

### 3. High Response Time
```
Trigger: response_time > 1000ms
Action: SET_DIMMER (reduce QoS)
Strategy: Threshold Reactive
```

### 4. Complex System Issues
```
Trigger: Multiple metrics anomalies
Action: LLM-generated recommendations
Strategy: Agentic LLM Reasoning
```

## Testing the System

### 1. Basic Connectivity Test
```bash
# Test SWIM connection
telnet localhost 4242
> get_servers
```

### 2. Generate Load on SWIM
Use SWIM's built-in load generation or external tools to create scenarios:
- High CPU utilization
- Memory pressure
- Network latency
- Server failures

### 3. Monitor Adaptations
Watch the console output for:
- Telemetry collection
- Threshold rule evaluations
- Action executions
- LLM reasoning traces

## Troubleshooting

### Common Issues

1. **SWIM Connection Failed**
   ```
   Error: Failed to connect to localhost:4242
   Solution: Ensure SWIM is running and accessible
   ```

2. **Google AI API Error**
   ```
   Error: LLM API call failed
   Solution: Check GOOGLE_AI_API_KEY is set correctly
   ```

3. **Import Errors**
   ```
   Error: ModuleNotFoundError
   Solution: Run setup_environment.py to configure Python path
   ```

4. **Configuration Errors**
   ```
   Error: Configuration validation failed
   Solution: Check config/swim_system_config.yaml syntax
   ```

### Debug Mode
Enable debug logging:
```bash
export POLARIS_FRAMEWORK__LOGGING_CONFIG__LEVEL=DEBUG
python run_swim_system.py
```

## Customization

### Adding New Threshold Rules
Edit `config/swim_system_config.yaml`:
```yaml
control_reasoning:
  threshold_reactive:
    rules:
      - rule_id: "custom_rule"
        name: "Custom Adaptation Rule"
        conditions:
          - metric_name: "your_metric"
            operator: "gt"
            value: 100
        action_type: "YOUR_ACTION"
        priority: 2
```

### Modifying LLM Behavior
Adjust LLM parameters:
```yaml
llm:
  temperature: 0.05  # More deterministic
  max_tokens: 3000   # Longer responses
  model_name: "gemini-1.5-flash"  # Faster model
```

### Adding Custom Metrics
Extend the SWIM connector to collect additional metrics from your system.

## Performance Considerations

- **Collection Interval**: Set to 10 seconds for responsive adaptation
- **LLM Cache**: 5-minute TTL to balance freshness and performance
- **Action Cooldowns**: Prevent adaptation thrashing
- **Concurrent Actions**: Limited to 3 for system stability

## Production Deployment

For production use:
1. Use persistent data storage (not in-memory)
2. Configure proper logging and monitoring
3. Set up distributed tracing
4. Use environment-specific configurations
5. Implement proper error handling and recovery
6. Set up health checks and alerting

## Support

For issues and questions:
1. Check the logs in `./logs/polaris.log`
2. Verify configuration in `config/swim_system_config.yaml`
3. Test individual components using the setup script
4. Review the system architecture and component interactions