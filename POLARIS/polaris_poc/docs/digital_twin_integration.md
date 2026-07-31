# Digital Twin Integration for POLARIS Framework

This document describes how the Digital Twin component integrates with the existing POLARIS telemetry and execution streams to provide real-time system knowledge updates.

## Overview

The Digital Twin integration works by subscribing to existing POLARIS NATS streams rather than requiring adapters to publish to specific Digital Twin topics. This approach:

- **Maintains Adapter Simplicity**: No changes required to Monitor or Execution adapters
- **Leverages Existing Streams**: Uses standard telemetry and execution result topics
- **Provides Automatic Integration**: Digital Twin automatically processes all system events

The Digital Twin subscribes to:
- **Telemetry Events**: Real-time metrics and measurements from Monitor adapters
- **Execution Status Events**: Results and outcomes of control actions from Execution adapters

This integration enables the Digital Twin to maintain an up-to-date world model of the managed system state without requiring adapter modifications.

## Configuration

### NATS Topics

The Digital Twin subscribes to the following existing POLARIS NATS topics:

- **Telemetry Batch**: `polaris.telemetry.events.batch` - Batched telemetry events from Monitor adapters
- **Telemetry Stream**: `polaris.telemetry.events.stream` - Individual telemetry events from Monitor adapters  
- **Execution Results**: `polaris.execution.results` - Execution results from Execution adapters
- **Calibrate Topic**: `polaris.digitaltwin.calibrate` - Model calibration feedback (future use)

### Digital Twin Configuration

Digital Twin NATS configuration in `polaris_config.yaml`:

```yaml
digital_twin:
  nats:
    calibrate_subject: "polaris.digitaltwin.calibrate"
    error_subject: "polaris.digitaltwin.errors"
    queue_group: "digital_twin_workers"
    max_reconnect_attempts: 10
    reconnect_wait_sec: 2
    queue_maxsize: 1000
    batch_size: 10
    batch_timeout_sec: 1.0
```

No adapter configuration changes are required - the Digital Twin automatically subscribes to existing streams.

## Integration Details

### Digital Twin Subscription Processing

The Digital Twin automatically subscribes to and processes events from existing POLARIS streams:

#### Telemetry Batch Processing

1. **Subscription**: Digital Twin subscribes to `polaris.telemetry.events.batch`
2. **Batch Processing**: Each `TelemetryBatch` is unpacked into individual telemetry events
3. **Knowledge Event Creation**: Each telemetry event is wrapped in a `KnowledgeEvent` for internal processing
4. **World Model Update**: Events are sent to the World Model for state tracking

**Original Telemetry Batch Structure**:
```json
{
  "batch_id": "uuid",
  "batch_timestamp": "2025-08-15T10:30:00Z",
  "count": 2,
  "events": [
    {
      "name": "cpu.usage",
      "value": 85.3,
      "unit": "percent",
      "timestamp": "2025-08-15T10:30:00Z",
      "source": "system_monitor"
    }
  ]
}
```

#### Telemetry Stream Processing

1. **Subscription**: Digital Twin subscribes to `polaris.telemetry.events.stream`
2. **Individual Processing**: Each `TelemetryEvent` is processed individually
3. **Knowledge Event Creation**: Events are wrapped for World Model consumption

#### Execution Result Processing

1. **Subscription**: Digital Twin subscribes to `polaris.execution.results`
2. **Result Processing**: Each `ExecutionResult` is processed as an execution status update
3. **Action Tracking**: Digital Twin tracks action outcomes for system state evolution

**Original Execution Result Structure**:
```json
{
  "action_id": "action-123",
  "action_type": "ADD_SERVER",
  "status": "success",
  "success": true,
  "message": "Successfully added server",
  "started_at": "2025-08-15T10:30:00Z",
  "finished_at": "2025-08-15T10:30:05Z",
  "duration_sec": 5.0
}
```

## Error Handling

The integration includes robust error handling:

- **Non-blocking**: Digital Twin subscription failures do not affect adapter operation
- **Dead Letter Queue**: Failed messages are sent to `polaris.digitaltwin.errors` topic
- **Logging**: All integration events and errors are logged for debugging
- **Graceful Degradation**: If Digital Twin is unavailable, adapters continue normal operation
- **Queue Management**: Message processing uses queues with configurable limits

## Verification

Use the verification script to test the integration:

```bash
cd polaris_poc
python scripts/verify_digital_twin_integration.py
```

This script:
1. Subscribes to the Digital Twin update topic
2. Publishes test events
3. Reports on received events
4. Verifies the integration is working

## Requirements Satisfied

This integration satisfies the following requirements:

- **Requirement 8.1**: Digital Twin processes telemetry from Monitor adapters via existing streams
- **Requirement 8.2**: Digital Twin processes execution status from Execution adapters via existing streams
- **Requirement 8.4**: Configuration options for Digital Twin NATS integration

## Usage Examples

### Starting Components

```bash
# Start Monitor adapter (publishes to standard telemetry streams)
python -m polaris.adapters.monitor --config config/polaris_config.yaml --plugin plugins/my_system

# Start Execution adapter (publishes to standard execution streams)
python -m polaris.adapters.execution --config config/polaris_config.yaml --plugin plugins/my_system

# Start Digital Twin (automatically subscribes to all streams)
python scripts/start_digital_twin.py --config config/polaris_config.yaml
```

### No Adapter Changes Required

The adapters require no modifications - they continue publishing to their standard NATS topics:
- Monitor adapters → `polaris.telemetry.events.batch` and `polaris.telemetry.events.stream`
- Execution adapters → `polaris.execution.results`

The Digital Twin automatically subscribes to these existing streams.

## Troubleshooting

### Common Issues

1. **No events received**: Check that NATS server is running and Digital Twin is subscribed
2. **Connection errors**: Verify NATS URL and network connectivity
3. **Permission errors**: Ensure NATS permissions allow publishing to Digital Twin topics

### Debug Logging

Enable debug logging to see integration details:

```yaml
logger:
  level: "DEBUG"
```

This will show:
- Digital Twin subscription and processing activities
- Event conversion from telemetry/execution to knowledge events
- World Model update operations
- Queue processing and batch handling