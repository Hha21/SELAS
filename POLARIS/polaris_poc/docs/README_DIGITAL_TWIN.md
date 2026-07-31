# POLARIS Digital Twin Component

The Digital Twin component provides intelligent system modeling and predictive capabilities for the POLARIS framework. It serves as the central "World Model" that maintains an up-to-date understanding of the managed system state and provides query, simulation, diagnosis, and management capabilities.

## 🏗️ Architecture

The Digital Twin implements a hybrid interface architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    Digital Twin Agent                       │
├─────────────────────────────────────────────────────────────┤
│  NATS Ingestion Engine          │  gRPC Service Interface   │
│  ┌─────────────────────────────┐│  ┌─────────────────────────┐│
│  │ • Telemetry Batch Handler   ││  │ • Query Service         ││
│  │ • Telemetry Stream Handler  ││  │ • Simulation Service    ││
│  │ • Execution Result Handler  ││  │ • Diagnosis Service     ││
│  │ • Calibration Handler       ││  │ • Management Service    ││
│  │ • Dead Letter Queue         ││  │ • Health Monitoring     ││
│  └─────────────────────────────┘│  └─────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│                    World Model Interface                    │
├─────────────────────────────────────────────────────────────┤
│  Mock Model    │  Gemini LLM   │  Statistical  │  Hybrid    │
│  ┌───────────┐ │  ┌───────────┐│  ┌───────────┐│  ┌────────┐│
│  │ Simple    │ │  │ LangChain ││  │ ML Models ││  │ Multi- ││
│  │ Responses │ │  │ Integration││  │ Time Series││  │ Model  ││
│  │ Testing   │ │  │ Reasoning ││  │ Analysis  ││  │ Fusion ││
│  └───────────┘ │  └───────────┘│  └───────────┘│  └────────┘│
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- NATS Server running
- gRPC dependencies (`pip install grpcio grpcio-tools`)
- For Gemini LLM: `pip install google-generativeai langchain`

### Starting the Digital Twin
```bash
# Basic startup
python src/scripts/start_digital_twin.py

# With specific World Model
python src/scripts/start_digital_twin.py --world-model gemini

# Validate configuration only
python src/scripts/start_digital_twin.py --validate-only

# Health check
python src/scripts/start_digital_twin.py --health-check

# Debug mode
python src/scripts/start_digital_twin.py --log-level DEBUG
```

### Verification
```bash
# Verify integration with adapters
python scripts/verify_digital_twin_integration.py

# Run comprehensive tests
python scripts/test_digital_twin_integration.py
```

## 🔧 Configuration

### Framework Configuration (`src/config/polaris_config.yaml`)

```yaml
digital_twin:
  # NATS configuration
  nats:
    calibrate_subject: "polaris.digitaltwin.calibrate"
    error_subject: "polaris.digitaltwin.errors"
    queue_group: "digital_twin_workers"
    max_reconnect_attempts: 10
    reconnect_wait_sec: 2
    queue_maxsize: 1000
    batch_size: 10
    batch_timeout_sec: 1.0
  
  # gRPC configuration
  grpc:
    host: "0.0.0.0"
    port: 50051
    max_workers: 10
    max_message_size: 4194304  # 4MB
    keepalive_time_ms: 30000
    keepalive_timeout_ms: 5000
  
  # World Model configuration
  world_model:
    implementation: "mock"  # "mock", "gemini", "statistical", "hybrid"
    config_path: "config/world_model.yaml"
    reload_on_failure: true
    health_check_interval_sec: 60
  
  # Performance settings
  performance:
    max_concurrent_queries: 10
    query_timeout_sec: 30
    simulation_timeout_sec: 60
  
  # Debugging and logging
  debugging:
    log_level: "DEBUG"
    enable_detailed_logging: true
    log_to_console: true
    log_file: "logs/digital_twin.log"
```

## 🔌 Integration with POLARIS

### Automatic Event Processing

The Digital Twin automatically subscribes to existing POLARIS NATS streams:

1. **Telemetry Integration**:
   - Subscribes to `polaris.telemetry.events.batch` (batched telemetry)
   - Subscribes to `polaris.telemetry.events.stream` (individual telemetry)
   - Converts telemetry events to `KnowledgeEvent` objects
   - Updates World Model with system metrics

2. **Execution Integration**:
   - Subscribes to `polaris.execution.results` (action results)
   - Converts execution results to `KnowledgeEvent` objects
   - Tracks action outcomes for system state evolution

3. **No Adapter Changes Required**:
   - Monitor and Execution adapters continue publishing to standard topics
   - Digital Twin processes events transparently
   - Clean separation of concerns

### Event Flow
```
Monitor Adapter → polaris.telemetry.events.* → Digital Twin → World Model
Execution Adapter → polaris.execution.results → Digital Twin → World Model
```

## 🌐 gRPC Services

### Query Service
Query current or historical system state.

```python
import grpc
from polaris.proto import digital_twin_pb2, digital_twin_pb2_grpc

channel = grpc.insecure_channel('localhost:50051')
stub = digital_twin_pb2_grpc.DigitalTwinStub(channel)

# Query current state
request = digital_twin_pb2.QueryRequest(
    query_type="current_state",
    query_content="What is the current CPU usage?",
    parameters={"system": "web_cluster"}
)

response = stub.Query(request)
print(f"Result: {response.result}")
print(f"Confidence: {response.confidence}")
```

### Simulation Service
Perform predictive "what-if" analysis.

```python
# Define actions to simulate
action = digital_twin_pb2.ControlAction(
    action_type="ADD_SERVER",
    target="web_cluster",
    params={"count": "2"},
    priority="normal"
)

# Create simulation request
request = digital_twin_pb2.SimulationRequest(
    simulation_type="what_if",
    actions=[action],
    horizon_minutes=60,
    parameters={"scenario": "traffic_spike"}
)

response = stub.Simulate(request)
print(f"Future states: {len(response.future_states)}")
print(f"Confidence: {response.confidence}")
```

### Diagnosis Service
Perform root cause analysis.

```python
# Request diagnosis
request = digital_twin_pb2.DiagnosisRequest(
    anomaly_description="High response times detected",
    context={
        "metric": "response_time",
        "value": "2500ms",
        "threshold": "500ms"
    }
)

response = stub.Diagnose(request)
for hypothesis in response.hypotheses:
    print(f"Hypothesis: {hypothesis.hypothesis}")
    print(f"Probability: {hypothesis.probability}")
```

### Management Service
Manage Digital Twin lifecycle and health.

```python
# Health check
request = digital_twin_pb2.ManagementRequest(
    operation="health_check"
)

response = stub.Manage(request)
print(f"Status: {response.health_status.status}")
print(f"Issues: {response.health_status.issues}")
```

## 🧠 World Model Implementations

### Mock Model (Default)
- **Purpose**: Testing and development
- **Features**: Simple predefined responses
- **Use Case**: Development, testing, demonstrations

### Gemini LLM Model
- **Purpose**: Natural language reasoning and analysis
- **Features**: 
  - LangChain integration
  - Natural language query processing
  - Contextual reasoning
  - Pattern recognition
- **Setup**: Requires `GEMINI_API_KEY` environment variable
- **Use Case**: Complex reasoning, natural language interfaces

### Statistical Model
- **Purpose**: Time series analysis and forecasting
- **Features**:
  - Statistical modeling
  - Trend analysis
  - Anomaly detection
  - Predictive forecasting
- **Use Case**: Performance prediction, capacity planning

### Hybrid Model
- **Purpose**: Multi-model fusion
- **Features**:
  - Combines multiple approaches
  - Confidence-weighted responses
  - Fallback mechanisms
- **Use Case**: Production environments requiring robustness

## 📊 Monitoring and Observability

### Health Monitoring
```bash
# Check Digital Twin health
python src/scripts/start_digital_twin.py --health-check

# Get detailed metrics via gRPC
grpcurl -plaintext localhost:50051 polaris.digitaltwin.DigitalTwin/Manage \
  -d '{"operation": "get_metrics"}'
```

### Performance Metrics
- Message processing throughput
- Queue sizes and high water marks
- gRPC request latencies
- World Model response times
- Error rates and dead letter queue usage

### Logging
```bash
# Enable debug logging
python src/scripts/start_digital_twin.py --log-level DEBUG

# View logs
tail -f logs/digital_twin.log
```

## 🧪 Testing and Validation

### Integration Tests
```bash
# Verify NATS integration
python scripts/verify_digital_twin_integration.py

# Comprehensive integration test
python scripts/test_digital_twin_integration.py

# Test specific World Model
python scripts/test_digital_twin_integration.py --world-model gemini
```

### Manual Testing
```bash
# Start full system
python src/scripts/start_component.py monitor --plugin-dir extern &
python src/scripts/start_component.py execution --plugin-dir extern &
python src/scripts/start_digital_twin.py &

# Test gRPC endpoints
grpcurl -plaintext localhost:50051 list polaris.digitaltwin.DigitalTwin
grpcurl -plaintext localhost:50051 polaris.digitaltwin.DigitalTwin/Query \
  -d '{"query_type": "current_state", "query_content": "system status"}'
```

### Load Testing
```bash
# Generate test load
python scripts/generate_test_load.py --telemetry-rate 100 --duration 300

# Monitor performance
python scripts/monitor_digital_twin_performance.py
```

## 🔧 Development and Extension

### Adding New World Model Implementation

1. **Implement World Model Interface**:
```python
from polaris.models.world_model import WorldModel

class MyWorldModel(WorldModel):
    async def initialize(self):
        # Initialize your model
        pass
    
    async def query_state(self, request):
        # Implement query logic
        pass
    
    async def simulate(self, request):
        # Implement simulation logic
        pass
```

2. **Register with Factory**:
```python
from polaris.models.world_model import WorldModelFactory

WorldModelFactory.register_model("my_model", MyWorldModel)
```

3. **Update Configuration**:
```yaml
digital_twin:
  world_model:
    implementation: "my_model"
```

### Custom Event Processing

1. **Extend Digital Twin Agent**:
```python
class CustomDigitalTwinAgent(DigitalTwinAgent):
    async def _handle_custom_message(self, msg):
        # Custom message processing
        pass
```

2. **Add Custom Subscriptions**:
```python
await self.nats_client.subscribe(
    "custom.events",
    self._handle_custom_message
)
```

## 🚨 Troubleshooting

### Common Issues

1. **gRPC Connection Failed**
   ```bash
   # Check if port is available
   netstat -an | grep 50051
   
   # Test gRPC connectivity
   grpcurl -plaintext localhost:50051 list
   ```

2. **NATS Subscription Issues**
   ```bash
   # Check NATS connectivity
   nats sub "polaris.telemetry.>"
   
   # Verify Digital Twin subscriptions
   python scripts/verify_digital_twin_integration.py
   ```

3. **World Model Initialization Failed**
   ```bash
   # Validate configuration
   python src/scripts/start_digital_twin.py --validate-only
   
   # Check World Model health
   python src/scripts/start_digital_twin.py --health-check
   ```

4. **High Memory Usage**
   - Reduce `queue_maxsize` in configuration
   - Decrease `batch_size` for processing
   - Enable message batching timeouts

5. **Slow Response Times**
   - Increase `max_workers` for gRPC
   - Optimize World Model implementation
   - Enable concurrent query processing

### Debug Steps
1. Enable debug logging (`--log-level DEBUG`)
2. Run health check (`--health-check`)
3. Validate configuration (`--validate-only`)
4. Check NATS connectivity
5. Test gRPC endpoints individually
6. Monitor performance metrics

## 📚 API Reference

### gRPC Service Definition
See `src/polaris/proto/digital_twin.proto` for complete API specification.

### Python Client Examples
See `examples/digital_twin_client.py` for comprehensive usage examples.

### Configuration Schema
See `src/config/digital_twin.schema.json` for configuration validation schema.

## 🔮 Future Enhancements

- **Multi-tenant Support**: Isolated World Models per system
- **Distributed Processing**: Horizontal scaling capabilities
- **Advanced Analytics**: ML-powered anomaly detection
- **Real-time Dashboards**: Web-based monitoring interface
- **API Gateway**: REST API wrapper for gRPC services
- **Event Sourcing**: Complete event history and replay capabilities