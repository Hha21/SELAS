#!/usr/bin/env python3
"""
POLARIS SWIM System Runner

Main entry point for running the POLARIS framework with SWIM system,
threshold-based reactive strategy, and LLM reasoning with Google AI.
"""

import asyncio
import logging
import os
import signal
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.framework.polaris_framework import PolarisFramework
from src.framework.configuration.builder import ConfigurationBuilder
from src.infrastructure.exceptions import PolarisException


class SwimSystemRunner:
    """Main runner for the SWIM system with POLARIS framework."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "config/swim_system_config.yaml"
        self.framework: Optional[PolarisFramework] = None
        self.logger = None  # Will be initialized after logging configuration
        self._shutdown_event = asyncio.Event()
        # Metrics logging defaults (can be overridden by env vars or config)
        self.metrics_interval = int(os.environ.get("POLARIS_METRICS_INTERVAL", "10"))
        self.metrics_log_path = os.environ.get("POLARIS_METRICS_LOG_PATH", "./logs/polaris_metrics.log")
        self._metrics_task: Optional[asyncio.Task] = None
        
    async def setup_framework(self) -> None:
        """Set up the POLARIS framework with SWIM configuration."""
        try:
            # Build configuration
            config_builder = ConfigurationBuilder()
            
            # Add YAML configuration file
            if os.path.exists(self.config_path):
                config_builder.add_yaml_source(self.config_path, priority=100)
                print(f"Loaded configuration from {self.config_path}")  # Use print before logger is configured
            else:
                print(f"Configuration file not found: {self.config_path}")
                
            # Add environment variables with POLARIS prefix
            config_builder.add_environment_source("POLARIS_", priority=200)
            
            # Add defaults
            config_builder.add_defaults()
            
            # Build configuration
            configuration = config_builder.build()
            
            # Wait for configuration to load (it's async)
            await configuration.wait_for_load()
            
            # Configure BOTH logging systems early based on the loaded configuration
            from src.infrastructure.observability import configure_logging
            from src.infrastructure.observability.factory import configure_logging as configure_polaris_logging
            try:
                framework_config = configuration.get_framework_config()
                

                # Configure standard Python logging
                configure_logging(framework_config.logging_config)
                
                # Configure POLARIS structured logging system
                configure_polaris_logging(framework_config.logging_config)
                
                # Now we can safely create and use the logger
                self.logger = logging.getLogger("swim_system_runner")
                self.logger.info(f"Logging configured successfully with format: {framework_config.logging_config.format}")
            except Exception as e:
                # Fallback to basic logging
                logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                self.logger = logging.getLogger("swim_system_runner")
                self.logger.warning(f"Failed to configure logging from config, using defaults: {e}")
            
            # Create framework instance (simplified for now)
            # Note: This will need to be updated when all components are implemented
            from src.infrastructure.di import DIContainer
            from src.framework.events import PolarisEventBus
            from src.infrastructure.data_storage import DataStoreFactory
            from src.framework.plugin_management import PolarisPluginRegistry
            from src.infrastructure.message_bus import PolarisMessageBus
            
            # Create DI container
            container = DIContainer()
            
            # Create core components
            event_bus = PolarisEventBus()
            data_store = DataStoreFactory.create_in_memory_store()
            plugin_registry = PolarisPluginRegistry()
            message_bus = PolarisMessageBus()  # This will need implementation
            
            # Register components in DI container
            container.register_singleton(type(configuration), configuration)
            container.register_singleton(PolarisEventBus, event_bus)
            container.register_singleton(type(data_store), data_store)
            container.register_singleton(PolarisPluginRegistry, plugin_registry)
            
            # Create framework
            self.framework = PolarisFramework(
                container=container,
                configuration=configuration,
                message_bus=message_bus,
                data_store=data_store,
                plugin_registry=plugin_registry,
                event_bus=event_bus
            )
            
            # Update metrics interval from configuration if available
            if hasattr(configuration, 'observability') and hasattr(configuration.observability, 'metrics'):
                if hasattr(configuration.observability.metrics, 'collection_interval'):
                    self.metrics_interval = configuration.observability.metrics.collection_interval
                    self.logger.info(f"Using metrics interval from config: {self.metrics_interval}s")
            
            self.logger.info("POLARIS framework setup completed")
            
        except Exception as e:
            self.logger.error(f"Failed to setup framework: {e}", exc_info=True)
            raise PolarisException(
                "Framework setup failed",
                error_code="SETUP_ERROR",
                cause=e
            )
    
    async def start_system(self) -> None:
        """Start the SWIM system."""
        try:
            # Setup framework first (this will configure logging and create self.logger)
            await self.setup_framework()
            
            if self.logger:
                self.logger.info("Starting SWIM system with POLARIS framework...")
            else:
                print("Starting SWIM system with POLARIS framework...")
            
            # Start framework
            await self.framework.start()

            # Start background metrics logger
            try:
                await self._ensure_metrics_log_dir()
                self._metrics_task = asyncio.create_task(self._metrics_worker())
                if self.logger:
                    self.logger.info(f"Started metrics logger task, writing to {self.metrics_log_path}")
                else:
                    print(f"Started metrics logger task, writing to {self.metrics_log_path}")
            except Exception as e:
                if self.logger:
                    self.logger.warning("Failed to start metrics logger task", exc_info=True)
                else:
                    print(f"Failed to start metrics logger task: {e}")
            
            if self.logger:
                self.logger.info("SWIM system started successfully")
                self.logger.info("System is running. Press Ctrl+C to stop.")
            else:
                print("SWIM system started successfully")
                print("System is running. Press Ctrl+C to stop.")
            
            # Wait for shutdown signal
            await self._shutdown_event.wait()
            
        except KeyboardInterrupt:
            if self.logger:
                self.logger.info("Received shutdown signal")
            else:
                print("Received shutdown signal")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error starting system: {e}", exc_info=True)
            else:
                print(f"Error starting system: {e}")
            raise
        finally:
            await self.stop_system()
    
    async def stop_system(self) -> None:
        """Stop the SWIM system."""
        try:
            if self.framework and self.framework.is_running():
                if self.logger:
                    self.logger.info("Stopping SWIM system...")
                else:
                    print("Stopping SWIM system...")
                await self.framework.stop()
                if self.logger:
                    self.logger.info("SWIM system stopped successfully")
                else:
                    print("SWIM system stopped successfully")
            # Stop metrics task
            if self._metrics_task:
                try:
                    self._metrics_task.cancel()
                    await asyncio.wait_for(self._metrics_task, timeout=5)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    if self.logger:
                        self.logger.debug("Metrics task did not finish cleanly", exc_info=True)
                    else:
                        print(f"Metrics task did not finish cleanly: {e}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error stopping system: {e}", exc_info=True)
            else:
                print(f"Error stopping system: {e}")
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        if self.logger:
            self.logger.info(f"Received signal {signum}")
        else:
            print(f"Received signal {signum}")
        self._shutdown_event.set()

    async def _ensure_metrics_log_dir(self) -> None:
        """Ensure the directory for metrics log exists."""
        try:
            p = Path(self.metrics_log_path).parent
            p.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Unable to create metrics log dir for {self.metrics_log_path}", exc_info=True)
            else:
                print(f"Unable to create metrics log dir for {self.metrics_log_path}: {e}")

    async def _metrics_worker(self) -> None:
        """Background task that periodically writes metrics snapshot to file.

        Writes one JSON object per line with timestamp, metrics snapshot and optional framework status.
        """
        # Import here to avoid potential import cycles at module import time
        try:
            from src.infrastructure.observability.metrics import get_metrics_collector
            if self.logger:
                self.logger.debug("Successfully imported get_metrics_collector")
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to import get_metrics_collector: {e}")
            else:
                print(f"Failed to import get_metrics_collector: {e}")
            get_metrics_collector = None

        iteration = 0
        while not self._shutdown_event.is_set():
            iteration += 1
            if self.logger:
                self.logger.debug(f"Metrics worker iteration {iteration}")
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": None,
                "framework_status": None,
            }

            # Collect metrics from the PolarisMetricsCollector if available
            try:
                if get_metrics_collector:
                    mc = get_metrics_collector()
                    all_metrics = mc.get_all_metrics()
                    metrics_data = {}
                    
                    for name, metric in all_metrics.items():
                        try:
                            # Get the default value for each metric
                            value = metric.get_value()
                            metrics_data[name] = {
                                "type": metric.get_type().value,
                                "value": value.value,
                                "labels": value.labels,
                                "timestamp": value.timestamp.isoformat()
                            }
                        except Exception as metric_error:
                            metrics_data[name] = {"error": str(metric_error)}

                    entry['metrics'] = metrics_data
                else:
                    entry['metrics'] = {"error": "metrics collector unavailable"}
            except Exception as e:
                entry['metrics'] = {"error": str(e)}

            # Add framework status snapshot if available
            try:
                if self.framework:
                    # get_status returns basic primitives
                    entry['framework_status'] = self.framework.get_status()
            except Exception as e:
                entry['framework_status'] = {"error": str(e)}

            # Append to file as JSON line
            try:
                with open(self.metrics_log_path, 'a') as fh:
                    fh.write(json.dumps(entry, default=str) + "\n")
                if self.logger:
                    self.logger.debug(f"Wrote metrics entry {iteration} to {self.metrics_log_path}")
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Failed to write metrics to {self.metrics_log_path}: {e}", exc_info=True)
                else:
                    print(f"Failed to write metrics to {self.metrics_log_path}: {e}")

            # Sleep until next collection interval or until shutdown
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=self.metrics_interval)
            except asyncio.TimeoutError:
                # timeout expired -> loop again
                pass


async def main():
    """Main entry point."""
    # Note: Logging will be configured by the framework based on configuration file
    # Don't setup basic logging here as it will override the POLARIS logging system
    
    # Check for Google AI API key
    if not os.getenv("GOOGLE_AI_API_KEY"):
        print("WARNING: GOOGLE_AI_API_KEY environment variable not set!")
        print("Please set your Google AI API key:")
        print("export GOOGLE_AI_API_KEY='your-api-key-here'")
        print()
        print("You can get an API key from: https://makersuite.google.com/app/apikey")
        print()
        
        # Ask if user wants to continue with mock LLM
        response = input("Continue with mock LLM for testing? (y/N): ")
        if response.lower() != 'y':
            sys.exit(1)
        
        # Set mock provider
        os.environ["POLARIS_LLM__PROVIDER"] = "mock"
        print("Using mock LLM provider for testing")
    
    # Create and run system
    runner = SwimSystemRunner()
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, runner.signal_handler)
    signal.signal(signal.SIGTERM, runner.signal_handler)
    
    try:
        await runner.start_system()
    except Exception as e:
        # Try to use the runner's logger if available, otherwise use basic logging
        if hasattr(runner, 'logger') and runner.logger:
            runner.logger.error(f"System failed: {e}", exc_info=True)
        else:
            print(f"System failed: {e}")
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())