# SWIM POLARIS Adaptation System

A complete self-adaptation system around SWIM (Simulated Web Infrastructure Manager) using the POLARIS framework architecture.

## Quick Start

### 1. Setup Environment

```bash
# Install Python dependencies
pip install -r requirements.txt

# Setup the environment
python scripts/setup_environment.py
```

### 2. Test Basic Functionality

```bash
# Run basic functionality test
python scripts/test_basic.py
```

### 3. Start the System

```bash
# Start with default configuration
python scripts/start_system.py --config config/base_config.yaml

# Or use the convenience script (Unix/Linux)
./scripts/start.sh

# Windows
scripts\start.bat
```

### 4. Monitor System Status

```bash
# Check system status
python scripts/system_status.py

# Continuous monitoring
python scripts/system_status.py --continuous
```

### 5. Run Ablation Studies

```bash
# List available studies
python scripts/run_ablation_study.py --list

# Run a specific study
python scripts/run_ablation_study.py --study full_system

# Run all studies
python scripts/run_ablation_study.py --all
```

## Directory Structure

```
polaris_refactored/plugins/swim/polaris_ablation/
├── config/                    # Configuration files
│   ├── base_config.yaml      # Base configuration
│   ├── development_config.yaml
│   ├── testing_config.yaml
│   ├── production_config.yaml
│   └── ablation_configs/     # Ablation study configurations
├── src/                      # Core implementation
│   ├── swim_driver.py        # Main driver application
│   ├── ablation_manager.py   # Ablation study management
│   ├── config_manager.py     # Configuration management
│   ├── logging_system.py     # Comprehensive logging
│   ├── metrics_system.py     # Metrics collection
│   └── config_templates.py   # Configuration templates
├── scripts/                  # Utility scripts
│   ├── start_system.py       # System startup
│   ├── run_ablation_study.py # Ablation study runner
│   ├── system_status.py      # Status monitoring
│   ├── setup_environment.py  # Environment setup
│   └── test_basic.py         # Basic functionality test
├── logs/                     # Log files
├── results/                  # Study results
└── requirements.txt          # Python dependencies
```

## Configuration

The system uses hierarchical YAML configuration with environment-specific overrides:

- `base_config.yaml` - Base configuration for all environments
- `development_config.yaml` - Development-specific settings
- `testing_config.yaml` - Testing environment settings
- `production_config.yaml` - Production environment settings

### Environment Variables

You can override configuration values using environment variables with the `SWIM_POLARIS_` prefix:

```bash
export SWIM_POLARIS_SWIM_HOST=192.168.1.100
export SWIM_POLARIS_SWIM_PORT=4242
export SWIM_POLARIS_LOG_LEVEL=DEBUG
```

## SWIM Integration

The system integrates with SWIM through the existing `SwimTCPConnector`. Ensure SWIM is running and accessible:

1. Start SWIM system
2. Verify SWIM is listening on the configured host/port (default: localhost:4242)
3. Test connection: `telnet localhost 4242`

## Ablation Studies

The system supports comprehensive ablation studies to evaluate component contributions:

### Available Studies

- `full_system` - All components enabled
- `no_learning` - System without learning engine
- `no_world_model` - System without world model
- `reactive_only` - Only reactive adaptation strategy
- `no_reasoning` - System without advanced reasoning

### Custom Studies

Create custom ablation configurations in `config/ablation_configs/`:

```yaml
ablation:
  description: "Custom study description"
  components:
    world_model: true
    knowledge_base: true
    learning_engine: false
    # ... other components
  study_parameters:
    duration: 3600  # seconds
    warmup_period: 300
    cooldown_period: 300
```

## Monitoring and Observability

The system provides comprehensive monitoring:

- **Structured Logging**: JSON-formatted logs with correlation IDs
- **Metrics Collection**: System and adaptation performance metrics
- **Health Monitoring**: Component health and system status
- **Real-time Status**: Live system monitoring and reporting

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all dependencies are installed and paths are correct
2. **SWIM Connection Failed**: Verify SWIM is running and accessible
3. **Configuration Errors**: Check YAML syntax and required fields
4. **Permission Errors**: Ensure write permissions for logs and results directories

### Debug Mode

Run with debug logging:

```bash
export SWIM_POLARIS_LOG_LEVEL=DEBUG
python scripts/start_system.py --config config/development_config.yaml
```

### Test Mode

Use testing configuration for faster cycles:

```bash
python scripts/start_system.py --config config/testing_config.yaml
```

## Development

### Adding New Components

1. Create component in `src/`
2. Add configuration schema
3. Update driver initialization
4. Add tests

### Adding New Ablation Studies

1. Create configuration in `config/ablation_configs/`
2. Define component combinations
3. Set study parameters
4. Test with `run_ablation_study.py`

## Architecture

The system implements a sophisticated layered architecture:

- **Infrastructure Layer**: Message bus, data storage, observability
- **Framework Layer**: Configuration, plugin management, events
- **Domain Layer**: Core models and interfaces
- **Adapter Layer**: System integration and monitoring
- **Digital Twin Layer**: World models, knowledge base, learning
- **Control & Reasoning Layer**: Adaptive control and reasoning

## License

This project is part of the POLARIS framework research initiative.