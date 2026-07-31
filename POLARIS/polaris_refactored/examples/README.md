# POLARIS Examples

This directory contains example implementations and demonstrations of various POLARIS framework components and features.

## Available Examples

### Control & Reasoning Examples

#### `threshold_reactive_strategy_example.py`
Demonstrates the usage of the ThresholdReactiveStrategy for rule-based adaptive control.

**Features demonstrated:**
- Configuration of threshold rules with various operators (GREATER_THAN, BETWEEN, etc.)
- Multi-condition rules with logical operators (AND, OR)
- Action prioritization and cooldown management
- Different threshold scenarios (CPU, memory, latency, error rates)
- Fallback behavior when no rules trigger

**Usage:**
```bash
cd polaris_refactored
python examples/threshold_reactive_strategy_example.py
```

#### `agentic_reasoning_example.py`
Shows how to use the agentic LLM reasoning system with fallback mechanisms.

**Features demonstrated:**
- LLM-based reasoning with tool integration
- Fallback to statistical/causal reasoning strategies
- Performance monitoring and strategy selection
- Multiple reasoning scenarios (CPU crisis, memory pressure, latency spikes)
- Integration with world model and knowledge base

**Usage:**
```bash
cd polaris_refactored
python examples/agentic_reasoning_example.py
```

### Infrastructure Examples

#### `llm_integration_example.py`
Demonstrates LLM integration patterns and best practices.

**Features demonstrated:**
- LLM client configuration and usage
- Error handling and retry mechanisms
- Response parsing and validation
- Integration with POLARIS observability

#### `enhanced_observability_example.py`
Shows comprehensive observability integration patterns.

**Features demonstrated:**
- Logging, metrics, and tracing integration
- Component-specific observability patterns
- Performance monitoring
- Error tracking and diagnostics

#### `observability_integration_example.py`
Demonstrates observability integration with various POLARIS components.

**Features demonstrated:**
- Cross-component observability
- Distributed tracing
- Metrics collection and aggregation
- Health monitoring

## Running Examples

### Prerequisites

1. Ensure you have Python 3.8+ installed
2. Install required dependencies (if any)
3. Set up any required environment variables (e.g., API keys for LLM examples)

### General Usage Pattern

Most examples can be run directly from the project root:

```bash
cd polaris_refactored
python examples/<example_name>.py
```

### Configuration

Examples use mock implementations by default to avoid external dependencies. To use real services:

1. **For LLM examples**: Set up OpenAI API key and modify the LLM configuration
2. **For database examples**: Configure connection strings
3. **For external service examples**: Set up appropriate credentials

### Example Output

Each example provides detailed logging output showing:
- Component initialization
- Execution flow
- Results and metrics
- Performance statistics
- Error handling (when applicable)

## Creating New Examples

When creating new examples:

1. Follow the existing naming convention: `<component>_<feature>_example.py`
2. Include comprehensive documentation and comments
3. Use mock implementations for external dependencies by default
4. Provide clear instructions for using real services
5. Include error handling and logging
6. Add the example to this README

### Example Template

```python
"""
<Component> Example

Brief description of what this example demonstrates.
"""

import asyncio
import logging
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

# Your imports here

async def main():
    """Main example function."""
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("Starting <Component> Example")
    
    # Your example code here
    
    logger.info("<Component> Example completed")

if __name__ == "__main__":
    asyncio.run(main())
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure you're running from the project root directory
2. **Missing Dependencies**: Check if additional packages need to be installed
3. **API Errors**: Verify API keys and endpoints are correctly configured
4. **Permission Errors**: Ensure proper file/directory permissions

### Getting Help

- Check the main project documentation in the `doc/` directory
- Review the component-specific documentation
- Look at the test files in `tests/` for additional usage patterns
- Check the source code for detailed implementation notes