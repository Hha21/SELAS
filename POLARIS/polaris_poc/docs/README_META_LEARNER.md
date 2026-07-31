# Meta-Learner Agent for POLARIS

## Implementation Summary

### Files Created

1. **`/src/polaris/agents/meta_learner_agent.py`** - Main interface with abstract base class and data models
2. **`/src/polaris/agents/example_meta_learner.py`** - Concrete implementation demonstrating the interface
3. **`/src/polaris/agents/__init__.py`** - Clean module exports
4. **`/tests/test_meta_learner_agent.py`** - Comprehensive test suite

## Overview

The Meta-Learner Agent provides meta-level learning capabilities for the POLARIS self-adaptive framework. It operates at the adaptation-strategy level rather than handling individual adaptation outcomes, focusing on continuous improvement of the overall adaptation system.

The Meta-Learner Agent is designed to:

- **Analyze aggregated adaptation patterns** from the knowledge base
- **Calibrate the world model** (digital twin) to maintain accuracy
- **Update adaptation system parameters** such as utility weights, policy parameters, and coordination strategies
- **Provide confidence estimates** for proposed parameter updates
- **Support multiple triggering mechanisms** (periodic, event-driven, performance-driven)
- **Remain implementation-agnostic** for different meta-learning approaches

## Recent Enhancements (September 2025)

### **Added NATS Communication & Service Integration**

The base class now includes full NATS communication capabilities and seamless integration with POLARIS services:

#### **Knowledge Base Integration**

- Query adaptation patterns and decisions from KB via NATS
- Query performance trends and system observations
- Store meta-learning insights back to KB
- Consistent with existing KB interface and models

#### **Digital Twin Integration**

- Query Digital Twin for calibration requests via NATS
- Handle DT responses with confidence and metrics
- Graceful fallbacks when DT unavailable
- Consistent with DT gRPC interface patterns

#### **NATS Communication**

- Full NATS integration consistent with other POLARIS agents
- Connection management and error handling
- System notification handling (shutdown, health checks)
- External trigger handling via NATS subjects

#### **Enhanced Base Class**

- Added `config_path` parameter for loading POLARIS framework configuration
- Added `nats_url` parameter (optional, loaded from config if not provided)
- Added configuration loading with environment variable overrides
- Maintains all existing abstract method signatures for backward compatibility

## Architecture

### Key Design Features

#### ✅ **Extensible Architecture**

- Abstract base class pattern allows easy plugging of different meta-learning approaches
- Support for Bayesian optimization, meta-RL, bandits, LLM-based strategies, etc.

#### ✅ **Knowledge Base Integration**

- Designed to work with existing POLARIS knowledge base
- Analyzes aggregated insights and reasoning patterns
- Can update knowledge base with learned insights

#### ✅ **World Model Calibration**

- Direct interface to calibrate the digital twin
- Maintains alignment between predictions and observed behavior
- Provides confidence estimates for calibration improvements

#### ✅ **Multi-Trigger Support**

- `PERIODIC` - Regular scheduled learning cycles
- `EVENT_DRIVEN` - Triggered by system events
- `PERFORMANCE_DRIVEN` - Triggered by performance degradation
- `THRESHOLD_VIOLATION` - Triggered by threshold breaches
- `MANUAL` - Human-initiated cycles

#### ✅ **Parameter Update Management**

- Updates utility weights, policy parameters, coordination strategies
- Confidence estimates for all proposed changes
- Safety validation and constraint checking
- Detailed reasoning and impact assessment

#### ✅ **Implementation Agnostic**

- Clean separation between interface and implementation
- New meta-learning methods can be added without system changes
- Follows POLARIS event-driven architecture principles

### Abstract Interface: `BaseMetaLearnerAgent`

The `BaseMetaLearnerAgent` provides an abstract base class that defines the contract for all meta-learning implementations. Key methods include:

- `analyze_adaptation_patterns()` - Extract insights from historical adaptation data
- `calibrate_world_model()` - Align the digital twin with observed system behavior
- `propose_parameter_updates()` - Generate parameter updates with confidence estimates
- `validate_updates()` - Perform safety checks and constraint validation
- `apply_updates()` - Execute validated parameter changes
- `handle_trigger()` - Process different types of meta-learning triggers

### Data Models

The interface uses strongly-typed data models:

- **`MetaLearningContext`** - Context information for learning cycles
- **`ParameterUpdate`** - Proposed parameter changes with confidence and reasoning
- **`CalibrationRequest/Result`** - World model calibration operations
- **`MetaLearningInsights`** - Aggregated analysis results

### Trigger Types

The agent supports multiple trigger mechanisms:

- **`PERIODIC`** - Regular scheduled learning cycles
- **`EVENT_DRIVEN`** - Triggered by specific system events
- **`PERFORMANCE_DRIVEN`** - Triggered by performance degradation
- **`THRESHOLD_VIOLATION`** - Triggered by threshold breaches
- **`MANUAL`** - Human-initiated learning cycles

## Alignment with POLARIS Architecture

The Meta-Learner Agent is fully aligned with the POLARIS v2 design:

1. **Event-Driven** - Supports NATS messaging and event triggers
2. **Decentralized** - Operates independently from other agents
3. **Multi-Objective** - Updates utility weights for performance/cost/reliability balance
4. **Formal Assurance** - Provides confidence estimates and safety validation
5. **Modular** - Plug-and-play design with standardized interfaces
6. **Meta-Learning Focus** - Operates at the strategy level as described in the architecture

## Usage Examples

### ✨ **NEW: Enhanced Usage with NATS Integration**

```python
from polaris.agents import ExampleMetaLearnerAgent
from polaris.agents.meta_learner_agent import MetaLearningContext, TriggerType

# Initialize meta-learner with NATS and service integration
agent = ExampleMetaLearnerAgent(
    agent_id="meta-learner-1",
    config_path="path/to/polaris_config.yaml",
    nats_url="nats://localhost:4222"  # optional
)

# Connect to NATS and services
await agent.connect()

# Query knowledge base for adaptation patterns
patterns = await agent.query_adaptation_patterns(hours=24.0)

# Request world model calibration
response = await agent.request_world_model_calibration(
    target_metrics=["cpu_usage", "response_time"]
)

# Create learning context
context = MetaLearningContext(
    trigger_type=TriggerType.PERIODIC,
    trigger_source="scheduler",
    time_window_hours=24.0
)

# Execute meta-learning cycle with automatic insight storage
insights = await agent.analyze_adaptation_patterns(context)
updates = await agent.propose_parameter_updates(insights, context)
validated = await agent.validate_updates(updates)
results = await agent.apply_updates(validated)

# Store insights back to KB (automatically handled in triggers)
await agent.store_meta_learning_insights(insights)

# Clean shutdown
await agent.disconnect()
```

### Legacy Usage (Still Supported)

```python
# Previous constructor style still works with updates
agent = ExampleMetaLearnerAgent(
    agent_id="meta-learner-1",
    config_path="path/to/polaris_config.yaml",
    config={
        "min_confidence_threshold": 0.7,
        "analysis_window_hours": 24.0
    }
)
```

### Quick Trigger Handling

```python
# Handle different trigger types
await agent.handle_trigger(
    TriggerType.PERFORMANCE_DRIVEN,
    {
        "source": "monitoring_agent",
        "metrics": {"response_time": 1.5, "error_rate": 0.05},
        "focus_areas": ["performance", "reliability"]
    }
)
```

### World Model Calibration

```python
from polaris.agents.meta_learner_agent import CalibrationRequest

# Calibrate world model
calibration_request = CalibrationRequest(
    target_metrics=["cpu_usage", "memory_usage", "response_time"],
    calibration_data={
        "historical_predictions": [...],
        "actual_outcomes": [...]
    },
    validation_window_hours=1.0
)

result = await agent.calibrate_world_model(calibration_request)
print(f"Calibration improvement: {result.improvement_score}")
```

## Implementation Details

### ✨ **Enhanced Base Class Methods**

The `BaseMetaLearnerAgent` now provides built-in methods for seamless integration:

#### **Knowledge Base Integration**

- `query_adaptation_patterns(hours, limit)` - Query adaptation decisions and patterns
- `query_performance_trends(hours, limit)` - Query system performance observations
- `store_meta_learning_insights(insights)` - Store insights back to KB
- `query_knowledge_base(query_data)` - Generic KB query via NATS
- `get_kb_stats()` - Get KB statistics

#### **Digital Twin Integration**

- `query_digital_twin(query)` - Generic DT query via NATS
- `request_world_model_calibration(metrics, hours)` - Request calibration from DT

#### **NATS Communication**

- `connect()` / `disconnect()` - NATS connection management
- `publish(topic, message)` / `listen(topic, callback)` - Generic NATS messaging
- System notification handling (shutdown, health checks)
- External trigger handling via NATS subjects

### **Configuration Management**

```yaml
# polaris_config.yaml
nats:
  url: "nats://localhost:4222"

digital_twin:
  enabled: true

knowledge_base:
  enabled: true
```

### **Error Handling & Resilience**

- Graceful fallbacks when services unavailable
- Comprehensive error logging with context
- Connection retry and timeout handling
- Configurable timeouts for KB and DT requests

### **Benefits of Enhanced Implementation**

#### 🎯 **Minimal Code Changes**

- Enhanced base class without breaking existing abstract interface
- Updated example implementation with minimal changes
- Maintained backward compatibility where possible

#### 🎯 **Consistency with POLARIS Architecture**

- Uses same NATS communication patterns as other agents
- Follows same configuration loading approach
- Integrates with existing KB and DT services seamlessly

#### 🎯 **Easy Operation**

- Base class provides all necessary infrastructure
- Concrete implementations just need to inherit and use methods
- No need to manage NATS connections or message formatting manually

#### 🎯 **Production Ready**

- Proper error handling and logging
- Connection management and graceful shutdowns
- Configurable timeouts and retry logic
- Test coverage maintained

## Implementation Guidelines

### Creating Custom Meta-Learners

To implement a custom meta-learner:

1. **Inherit from `BaseMetaLearnerAgent`**
2. **Implement all abstract methods**
3. **Choose appropriate ML techniques** (e.g., Bayesian optimization, meta-RL, bandits)
4. **Integrate with knowledge base** for pattern analysis
5. **Provide confidence estimates** for all parameter updates

### Example Implementation Patterns

#### Bayesian Optimization Meta-Learner

```python
class BayesianMetaLearnerAgent(BaseMetaLearnerAgent):
    async def propose_parameter_updates(self, insights, context):
        # Use Gaussian Process for parameter optimization
        # Implement acquisition function for exploration/exploitation
        # Return updates with uncertainty-based confidence
        pass
```

#### Multi-Armed Bandit Meta-Learner

```python
class BanditMetaLearnerAgent(BaseMetaLearnerAgent):
    async def propose_parameter_updates(self, insights, context):
        # Use Thompson sampling for parameter selection
        # Update reward estimates based on adaptation outcomes
        # Return updates with probability-based confidence
        pass
```

#### LLM-Based Meta-Learner

```python
class LLMMetaLearnerAgent(BaseMetaLearnerAgent):
    async def analyze_adaptation_patterns(self, context):
        # Use LLM for pattern analysis and insight generation
        # Leverage RAG for historical context
        # Return structured insights with reasoning
        pass
```

## Integration with POLARIS Components

### Knowledge Base Integration

The meta-learner queries the knowledge base for:

- Historical adaptation decisions and outcomes
- System performance metrics and trends
- Anomaly patterns and frequencies
- Coordination effectiveness data

### World Model Integration

The meta-learner calibrates the world model by:

- Comparing predictions with actual outcomes
- Adjusting model parameters for better accuracy
- Validating improvements through historical data
- Maintaining uncertainty estimates

### Event-Driven Architecture

The meta-learner integrates with NATS messaging for:

- Receiving trigger events from other agents
- Publishing parameter update notifications
- Coordinating with other system components

## Configuration

### Agent Configuration

```yaml
meta_learner:
  agent_id: "meta-learner-primary"
  min_confidence_threshold: 0.7
  analysis_window_hours: 24.0
  calibration_frequency_hours: 6.0

  # Trigger configuration
  triggers:
    periodic:
      enabled: true
      interval_hours: 12.0
    performance_driven:
      enabled: true
      threshold_degradation: 0.1
    threshold_violation:
      enabled: true

  # Learning parameters
  learning:
    max_parameter_change: 0.2
    safety_constraints:
      - "utility_weights_sum_to_one"
      - "positive_control_gains"
```

## Error Handling

The interface defines specific exceptions:

- `MetaLearningError` - Base exception for meta-learning operations
- `CalibrationError` - World model calibration failures
- `ParameterUpdateError` - Parameter update generation failures
- `ValidationError` - Parameter validation failures
- `UpdateApplicationError` - Parameter application failures
- `TriggerHandlingError` - Trigger processing failures

## Testing

The framework includes comprehensive testing support:

- **Mock implementations** for testing
- **Validation of parameter update safety**
- **Confidence threshold testing**
- **Integration testing** with knowledge base and world model
- **19 test cases** covering all aspects of the interface

### Running Tests

```bash
cd /path/to/polaris_poc
PYTHONPATH=src python3 tests/test_meta_learner_agent.py
```

All tests pass successfully, ensuring the interface is robust and ready for production use.

## Next Steps

1. **✅ COMPLETED:** Enhanced with Knowledge Base and Digital Twin integration via NATS
2. **✅ COMPLETED:** Full NATS communication infrastructure
3. **✅ COMPLETED:** Configuration management and environment variable support
4. **Advanced Implementations** - Add Bayesian optimization, meta-RL, or LLM-based learners
5. **Enhanced Configuration** - Add more sophisticated YAML configuration templates
6. **Monitoring** - Add metrics collection and dashboard integration
7. **Production Testing** - Deploy in test environment for validation

The interface is **ready for immediate use** and can be extended with sophisticated machine learning approaches while maintaining the same clean contract.

## Future Extensions

The interface is designed to support future enhancements:

- Multi-objective meta-learning
- Federated meta-learning across multiple systems
- Explainable meta-learning with detailed reasoning
- Real-time meta-learning with streaming data
- Meta-learning of meta-learning strategies (meta-meta-learning)
