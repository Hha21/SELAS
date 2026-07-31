"""
SWIM POLARIS Driver Application

Main driver application that orchestrates the complete SWIM POLARIS adaptation system.
Initializes all components, manages the system lifecycle, and provides monitoring capabilities.
"""

import asyncio
import logging
import signal
import sys
import yaml
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

# Add POLARIS framework to path
polaris_root = Path(__file__).parent.parent.parent.parent.parent.parent
sys.path.append(str(polaris_root))

# POLARIS framework imports 
from polaris_refactored.src.domain.models import SystemState, HealthStatus, MetricValue, ExecutionStatus

src_root = Path(__file__).parent
sys.path.append(str(src_root))
# SWIM-specific 
from swim_adaptation_strategies import (
    SwimAdaptationStrategyFactory, SwimAdaptationCoordinator, AdaptationContext, AdaptationTrigger
)
from swim_metrics_processor import SwimMetricsProcessor, SwimMetricsAggregator


@dataclass
class SystemStatus:
    """Current status of the SWIM POLARIS system."""
    framework_running: bool = False
    swim_connected: bool = False
    adaptation_active: bool = False
    last_adaptation: Optional[datetime] = None
    total_adaptations: int = 0
    successful_adaptations: int = 0
    failed_adaptations: int = 0
    health_status: HealthStatus = HealthStatus.UNKNOWN
    uptime: float = 0.0
    last_update: Optional[datetime] = None
    system_metrics: Optional[Dict[str, Any]] = None
    component_status: Optional[Dict[str, HealthStatus]] = None
    recent_adaptations: Optional[List[Dict[str, Any]]] = None


class ConfigManager:
    """Handles configuration loading and merging."""
    
    @staticmethod
    def load_config(config_path: Path) -> Dict[str, Any]:
        """Load configuration with inheritance support."""
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Handle configuration inheritance
        if "extends" in config:
            base_config_path = config_path.parent / config["extends"]
            if base_config_path.exists():
                with open(base_config_path, 'r') as f:
                    base_config = yaml.safe_load(f)
                config = ConfigManager._merge_configs(base_config, config)
        
        return config
    
    @staticmethod
    def _merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge configuration dictionaries."""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigManager._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result


class SwimConnectorManager:
    """Manages SWIM connector instantiation."""
    
    @staticmethod
    def get_connector(swim_config: Dict[str, Any], logger: logging.Logger):
        """Get SWIM connector with proper import handling."""
        connector_path = Path(__file__).parent.parent.parent / "connector.py"
        
        if not connector_path.exists():
            raise ImportError("SWIM connector not found")
        
        spec = importlib.util.spec_from_file_location("swim_connector", connector_path)
        connector_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(connector_module)
        
        return connector_module.SwimTCPConnector(swim_config)


class ComponentManager:
    """Manages initialization of SWIM-specific components."""
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.metrics_processor: Optional[SwimMetricsProcessor] = None
        self.metrics_aggregator: Optional[SwimMetricsAggregator] = None
        self.adaptation_strategies: List = []
        self.adaptation_coordinator: Optional[SwimAdaptationCoordinator] = None
    
    async def initialize(self):
        """Initialize all SWIM components."""
        self.logger.info("Initializing SWIM components...")
        
        # Initialize metrics components
        metrics_config = self.config.get("metrics_processing", {})
        self.metrics_processor = SwimMetricsProcessor(metrics_config)
        
        aggregator_config = self.config.get("metrics_aggregation", {})
        self.metrics_aggregator = SwimMetricsAggregator(aggregator_config)
        
        # Initialize adaptation components
        self.adaptation_strategies = SwimAdaptationStrategyFactory.create_strategies_from_config(
            self.config
        )
        
        coordinator_config = self.config.get("control_reasoning", {}).get("adaptive_controller", {})
        self.adaptation_coordinator = SwimAdaptationCoordinator(
            self.adaptation_strategies, coordinator_config
        )
        
        self.logger.info(f"Initialized {len(self.adaptation_strategies)} adaptation strategies")


class TelemetryProcessor:
    """Handles telemetry collection and processing."""
    
    def __init__(self, component_manager: ComponentManager, config: Dict[str, Any], logger: logging.Logger):
        self.component_manager = component_manager
        self.config = config
        self.logger = logger
    
    async def collect_and_process(self, system_status: SystemStatus):
        """Collect and process telemetry from SWIM."""
        swim_config = self.config.get("managed_systems", [{}])[0].get("config", {})
        swim_connector = SwimConnectorManager.get_connector(swim_config, self.logger)
        
        # Collect system state
        system_state = await swim_connector.get_system_state()
        
        # Process metrics
        processed_metrics = await self.component_manager.metrics_processor.process_telemetry_event(system_state)
        self.component_manager.metrics_aggregator.add_metrics(processed_metrics.swim_metrics)
        
        # Update system status
        system_status.health_status = processed_metrics.health_status
        system_status.last_update = datetime.now(timezone.utc)
        system_status.system_metrics = system_state.metrics


class AdaptationEngine:
    """Handles adaptation decision and execution."""
    
    def __init__(self, component_manager: ComponentManager, config: Dict[str, Any], logger: logging.Logger):
        self.component_manager = component_manager
        self.config = config
        self.logger = logger
    
    async def execute_cycle(self, system_status: SystemStatus):
        """Execute one complete adaptation cycle (MAPE-K)."""
        # Get recent metrics for context
        recent_metrics = self.component_manager.metrics_processor.get_recent_metrics(10)
        if not recent_metrics:
            return
        
        current_metrics = recent_metrics[-1]
        context = AdaptationContext(
            current_metrics=current_metrics,
            historical_metrics=recent_metrics[:-1],
            system_state=None,
            trigger=AdaptationTrigger.THRESHOLD_VIOLATION,
            confidence=0.8,
            constraints=self.config.get("adaptation", {}).get("constraints", {})
        )
        
        # Check if adaptation is needed
        should_adapt, confidence, strategies = await self.component_manager.adaptation_coordinator.should_adapt(context)
        
        if should_adapt:
            self.logger.info(f"Adaptation needed (confidence: {confidence:.2f}, strategies: {strategies})")
            
            # Plan and execute adaptations
            actions = await self.component_manager.adaptation_coordinator.plan_adaptations(context)
            if actions:
                await self._execute_adaptations(actions, system_status)
    
    async def _execute_adaptations(self, actions, system_status: SystemStatus):
        """Execute adaptation actions."""
        self.logger.info(f"Executing {len(actions)} adaptation actions")
        
        swim_config = self.config.get("managed_systems", [{}])[0].get("config", {})
        swim_connector = SwimConnectorManager.get_connector(swim_config, self.logger)
        
        successful = 0
        failed = 0
        
        for action in actions:
            try:
                result = await swim_connector.execute_action(action)
                if result.status.value == "success":
                    successful += 1
                    self.logger.info(f"Action {action.action_type} executed successfully")
                else:
                    failed += 1
                    self.logger.warning(f"Action {action.action_type} failed: {result.result_data}")
            except Exception as e:
                failed += 1
                self.logger.error(f"Action {action.action_type} execution error: {e}")
        
        # Update statistics
        system_status.successful_adaptations += successful
        system_status.failed_adaptations += failed
        system_status.total_adaptations += len(actions)
        system_status.last_adaptation = datetime.now(timezone.utc)
        
        self.logger.info(f"Adaptation execution completed: {successful} successful, {failed} failed")


class SwimPolarisDriver:
    """Main driver for the SWIM POLARIS adaptation system."""
    
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config: Optional[Dict[str, Any]] = None
        self.logger: Optional[logging.Logger] = None
        
        # System components
        self.component_manager: Optional[ComponentManager] = None
        self.telemetry_processor: Optional[TelemetryProcessor] = None
        self.adaptation_engine: Optional[AdaptationEngine] = None
        
        # System state
        self.running = False
        self.start_time: Optional[datetime] = None
        self.system_status = SystemStatus()
        self.shutdown_event = asyncio.Event()
        
        # Setup signal handlers
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            print(f"\nReceived signal {signum}, initiating graceful shutdown...")
            asyncio.create_task(self._trigger_shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def _trigger_shutdown(self):
        """Trigger graceful shutdown."""
        self.shutdown_event.set()
    
    async def initialize(self) -> bool:
        """Initialize the SWIM POLARIS system."""
        print("Initializing SWIM POLARIS Adaptation System...")
        
        try:
            # Load configuration
            self.config = ConfigManager.load_config(self.config_path)
            print("Configuration loaded successfully")
            
            # Initialize logging
            self._setup_logging()
            
            # Initialize components
            self.component_manager = ComponentManager(self.config, self.logger)
            await self.component_manager.initialize()
            
            self.telemetry_processor = TelemetryProcessor(self.component_manager, self.config, self.logger)
            self.adaptation_engine = AdaptationEngine(self.component_manager, self.config, self.logger)
            
            # Verify SWIM connection
            await self._verify_swim_connection()
            
            # Update system status
            self.system_status.framework_running = True
            
            self.logger.info("SWIM POLARIS system initialized successfully")
            return True
            
        except Exception as e:
            print(f"Failed to initialize system: {e}")
            if self.logger:
                self.logger.error(f"System initialization failed: {e}")
            return False
    
    def _setup_logging(self):
        """Initialize logging system."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("swim_driver")
        self.logger.info("Logging system initialized")
    
    async def _verify_swim_connection(self):
        """Verify connection to SWIM system."""
        self.logger.info("Verifying SWIM connection...")
        
        swim_config = self.config.get("managed_systems", [{}])[0].get("config", {})
        swim_connector = SwimConnectorManager.get_connector(swim_config, self.logger)
        
        connected = await swim_connector.connect()
        if connected:
            self.system_status.swim_connected = True
            self.logger.info("SWIM connection verified")
        else:
            raise ConnectionError("Failed to connect to SWIM")
    
    async def run(self) -> int:
        """Run the SWIM POLARIS system."""
        try:
            if not await self.initialize():
                return 1
            
            self.running = True
            self.start_time = datetime.now(timezone.utc)
            self.system_status.adaptation_active = True
            
            self.logger.info("SWIM POLARIS system started successfully")
            print("SWIM POLARIS Adaptation System is running...")
            print("Press Ctrl+C to stop")
            
            await self._main_loop()
            return 0
            
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt")
            return 0
        except Exception as e:
            self.logger.error(f"System error: {e}")
            return 1
        finally:
            await self.shutdown()
    
    async def _main_loop(self):
        """Main processing loop."""
        self.logger.info("Starting main processing loop")
        
        # Get intervals from config
        collection_interval = self.config.get("managed_systems", [{}])[0].get("config", {}).get("implementation", {}).get("collection_interval", 10.0)
        adaptation_interval = self.config.get("control_reasoning", {}).get("adaptive_controller", {}).get("mape_k_interval", 30.0)
        
        tasks = [
            asyncio.create_task(self._telemetry_loop(collection_interval)),
            asyncio.create_task(self._adaptation_loop(adaptation_interval)),
            asyncio.create_task(self._status_loop()),
            asyncio.create_task(self.shutdown_event.wait())
        ]
        
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        
        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    async def _telemetry_loop(self, interval: float):
        """Telemetry processing loop."""
        self.logger.info("Starting telemetry processing loop")
        
        while self.running:
            try:
                await self.telemetry_processor.collect_and_process(self.system_status)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Telemetry processing error: {e}")
                self.system_status.health_status = HealthStatus.UNHEALTHY
                await asyncio.sleep(5.0)
    
    async def _adaptation_loop(self, interval: float):
        """Adaptation processing loop."""
        self.logger.info("Starting adaptation loop")
        
        while self.running:
            try:
                await self.adaptation_engine.execute_cycle(self.system_status)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Adaptation loop error: {e}")
                await asyncio.sleep(10.0)
    
    async def _status_loop(self):
        """Status monitoring loop."""
        while self.running:
            try:
                # Update uptime
                if self.start_time:
                    self.system_status.uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()
                
                # Log status
                self.logger.info("System Status", extra={
                    "framework_running": self.system_status.framework_running,
                    "swim_connected": self.system_status.swim_connected,
                    "adaptation_active": self.system_status.adaptation_active,
                    "total_adaptations": self.system_status.total_adaptations,
                    "successful_adaptations": self.system_status.successful_adaptations,
                    "failed_adaptations": self.system_status.failed_adaptations,
                    "current_health": self.system_status.health_status.value,
                    "uptime_seconds": self.system_status.uptime
                })
                
                await asyncio.sleep(60.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Status monitoring error: {e}")
                await asyncio.sleep(30.0)
    
    async def shutdown(self):
        """Gracefully shutdown the system."""
        if not self.running:
            return
        
        self.logger.info("Initiating system shutdown...")
        self.running = False
        self.system_status.framework_running = False
        self.logger.info("System shutdown completed")
    
    def get_system_status(self) -> SystemStatus:
        """Get current system status."""
        return self.system_status
    
    async def get_status(self) -> SystemStatus:
        """Get current system status (async version)."""
        if self.start_time:
            self.system_status.uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        return self.system_status
    
    async def start(self) -> None:
        """Start the system (for compatibility with ablation manager)."""
        await self.initialize()
        self.running = True
        self.start_time = datetime.now(timezone.utc)
        self.system_status.adaptation_active = True
        
        # Start background tasks
        collection_interval = self.config.get("managed_systems", [{}])[0].get("config", {}).get("implementation", {}).get("collection_interval", 10.0)
        adaptation_interval = self.config.get("control_reasoning", {}).get("adaptive_controller", {}).get("mape_k_interval", 30.0)
        
        self._background_tasks = [
            asyncio.create_task(self._telemetry_loop(collection_interval)),
            asyncio.create_task(self._adaptation_loop(adaptation_interval)),
            asyncio.create_task(self._status_loop())
        ]
    
    async def stop(self) -> None:
        """Stop the system (for compatibility with ablation manager)."""
        self.running = False
        
        if hasattr(self, '_background_tasks'):
            for task in self._background_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
        
        await self.shutdown()


async def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python swim_driver.py <config_file>")
        return 1
    
    config_file = sys.argv[1]
    driver = SwimPolarisDriver(config_file)
    
    return await driver.run()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)