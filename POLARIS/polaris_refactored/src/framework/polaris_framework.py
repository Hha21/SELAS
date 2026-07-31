"""
POLARIS Framework - Main orchestration class

This is the main entry point for the POLARIS framework, responsible for
initializing and coordinating all layers of the system with comprehensive
observability integration.
"""

import asyncio
from typing import Dict, List, Optional
import logging
from pathlib import Path


from ..infrastructure.di import DIContainer, Injectable
from ..infrastructure.exceptions import PolarisException, ConfigurationError
from ..infrastructure.message_bus import PolarisMessageBus
from ..infrastructure.data_storage import PolarisDataStore
from ..infrastructure.observability import (
    ObservabilityConfig, ObservabilityManager, get_logger, 
    initialize_observability, shutdown_observability, observe_polaris_component,
    configure_logging, get_framework_logger
)
from .configuration import PolarisConfiguration
from .plugin_management import PolarisPluginRegistry
from .events import PolarisEventBus


@observe_polaris_component("framework", auto_trace=True, auto_metrics=True, log_method_calls=True)
class PolarisFramework(Injectable):
    """
    Main POLARIS Framework class that orchestrates all system components.
    
    This class implements the Facade pattern to provide a simple interface
    for starting, stopping, and managing the entire POLARIS system with
    comprehensive observability integration.
    """
    
    def __init__(
        self,
        container: DIContainer,
        configuration: PolarisConfiguration,
        message_bus: PolarisMessageBus,
        data_store: PolarisDataStore,
        plugin_registry: PolarisPluginRegistry,
        event_bus: PolarisEventBus,
        observability_config: Optional[ObservabilityConfig] = None
    ):
        self.container = container
        self.configuration = configuration
        self.message_bus = message_bus
        self.data_store = data_store
        self.plugin_registry = plugin_registry
        self.event_bus = event_bus
        
        # Initialize observability first
        self.observability_config = observability_config or ObservabilityConfig()
        self.observability_manager = initialize_observability(self.observability_config)
        
        # Use POLARIS logger factory (will be configured during start())
        self.logger = get_framework_logger("main")
        self._running = False
        self._components: List[str] = []
        self._adapters: List = []  # Store adapter instances for cleanup
        self._subscriptions: List[str] = []  # Store event subscriptions for cleanup
    
    async def start(self) -> None:
        """
        Start the POLARIS framework and all its components.
        
        This method initializes all layers in the correct order:
        0. Observability layer (logging, metrics, tracing)
        1. Infrastructure layer (message bus, data store)
        2. Framework layer (plugin registry, event bus)
        3. Digital Twin layer
        4. Control & Reasoning layer
        5. Adapter layer
        """
        if self._running:
            # Use basic logging for this early warning since logging might not be configured yet
            print("WARNING: POLARIS framework is already running")
            return
        
        try:
            # Configure BOTH logging systems FIRST, before any other operations
            try:
                framework_config = self.configuration.get_framework_config()
                
                # Configure standard Python logging
                configure_logging(framework_config.logging_config)
                
                # Configure POLARIS structured logging system
                from ..infrastructure.observability.factory import configure_logging as configure_polaris_logging
                configure_polaris_logging(framework_config.logging_config)
                
                # Now we can safely use the logger
                self.logger = get_framework_logger("main")
            except Exception as e:
                # If configuration fails, use basic logging and continue
                import logging
                logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                self.logger = get_framework_logger("main")
                self.logger.warning("Failed to configure logging from framework config", extra={
                    "error": str(e)
                })
            
            # Initialize observability
            await self.observability_manager.initialize()
            self.logger.info("Starting POLARIS framework...", extra={
                "framework_version": "2.0.0",
                "service_name": self.observability_config.service_name
            })
            
            # Start infrastructure components
            await self._start_infrastructure()
            
            # Start framework components
            await self._start_framework_services()
            
            # Start digital twin components
            await self._start_digital_twin()
            
            # Start control and reasoning components
            await self._start_control_reasoning()
            
            # Start adapter components
            await self._start_adapters()
            
            self._running = True
            self.logger.info("POLARIS framework started successfully", extra={
                "components_started": len(self._components),
                "startup_duration_ms": "tracked_by_metrics"
            })
            
            # Update metrics
            metrics = self.observability_manager.get_metrics_collector()
            metrics.set_active_systems_count(len(self._components))
            
        except Exception as e:
            self.logger.error("Failed to start POLARIS framework", extra={
                "error": str(e),
                "error_type": type(e).__name__
            }, exc_info=e)
            await self._cleanup_on_failure()
            raise PolarisException(
                "Failed to start POLARIS framework",
                error_code="FRAMEWORK_START_ERROR",
                cause=e
            )
    
    async def stop(self) -> None:
        """
        Stop the POLARIS framework and all its components.
        
        Components are stopped in reverse order of startup.
        """
        if not self._running:
            self.logger.warning("POLARIS framework is not running")
            return
        
        try:
            self.logger.info("Stopping POLARIS framework...", extra={
                "components_to_stop": len(self._components)
            })
            
            # Stop components in reverse order
            await self._stop_adapters()
            await self._stop_control_reasoning()
            await self._stop_digital_twin()
            await self._stop_framework_services()
            await self._stop_infrastructure()
            
            self._running = False
            component_count = len(self._components)
            self._components.clear()
            
            # Update metrics
            metrics = self.observability_manager.get_metrics_collector()
            metrics.set_active_systems_count(0)
            
            self.logger.info("POLARIS framework stopped successfully", extra={
                "components_stopped": component_count
            })
            
            # Shutdown observability last
            await shutdown_observability()
            
        except Exception as e:
            self.logger.error("Error stopping POLARIS framework", extra={
                "error": str(e),
                "error_type": type(e).__name__
            }, exc_info=e)
            raise PolarisException(
                "Failed to stop POLARIS framework",
                error_code="FRAMEWORK_STOP_ERROR",
                cause=e
            )
    
    async def restart(self) -> None:
        """Restart the POLARIS framework."""
        await self.stop()
        await self.start()
    
    def is_running(self) -> bool:
        """Check if the framework is currently running."""
        return self._running
    
    def get_status(self) -> Dict[str, any]:
        """Get the current status of the framework and its components."""
        return {
            "running": self._running,
            "components": self._components.copy(),
            "configuration_loaded": self.configuration is not None,
            "message_bus_connected": hasattr(self.message_bus, '_connected') and self.message_bus._connected,
            "data_store_connected": hasattr(self.data_store, '_connected') and self.data_store._connected
        }
    
    async def _start_infrastructure(self) -> None:
        """Start infrastructure layer components."""
        self.logger.debug("Starting infrastructure layer...")
        
        # Start message bus
        await self.message_bus.start()
        self._components.append("message_bus")
        
        # Start data store
        await self.data_store.start()
        self._components.append("data_store")
        
        self.logger.debug("Infrastructure layer started")
    
    async def _start_framework_services(self) -> None:
        """Start framework layer services."""
        self.logger.debug("Starting framework services...")
        
        # Initialize plugin registry with search paths from configuration
        framework_config = self.configuration.get_framework_config()
        search_paths = []
        for p in framework_config.plugin_search_paths:
            path = Path(p)
            # If path is relative, resolve it relative to current working directory
            if not path.is_absolute():
                path = Path.cwd() / path
            # Resolve to get canonical path and check if it exists
            try:
                resolved_path = path.resolve()
                search_paths.append(resolved_path)
            except Exception as e:
                self.logger.warning(f"Could not resolve plugin search path {p}: {e}")
        
        await self.plugin_registry.initialize(search_paths=search_paths, enable_hot_reload=False)
        self._components.append("plugin_registry")
        
        # Start event bus
        await self.event_bus.start()
        self._components.append("event_bus")
        
        self.logger.debug("Framework services started")
    
    async def _start_digital_twin(self) -> None:
        """Start digital twin layer components."""
        self.logger.debug("Starting digital twin layer...")
        
        # Create and register digital twin components
        try:
            from ..digital_twin import PolarisWorldModel, PolarisKnowledgeBase, PolarisLearningEngine
            from ..digital_twin.world_model import StatisticalWorldModel
            from ..digital_twin.telemetry_subscriber import subscribe_telemetry_persistence
            from ..infrastructure.data_storage import DataStoreFactory
            
            # Create knowledge base with data store
            knowledge_base = PolarisKnowledgeBase(self.data_store)
            self.container.register_singleton(PolarisKnowledgeBase, knowledge_base)
            
            # Create world model (use statistical as default)
            world_model = StatisticalWorldModel(knowledge_base=knowledge_base)
            self.container.register_singleton(PolarisWorldModel, world_model)
            
            # Create learning engine
            learning_engine = PolarisLearningEngine(
                knowledge_base=knowledge_base,
                world_model=world_model
            )
            self.container.register_singleton(PolarisLearningEngine, learning_engine)
            
            # Start components if they have start methods
            if hasattr(world_model, 'start'):
                await world_model.start()
            if hasattr(knowledge_base, 'start'):
                await knowledge_base.start()
            if hasattr(learning_engine, 'start'):
                await learning_engine.start()
            
            # Subscribe telemetry handler to event bus
            subscription_id = await subscribe_telemetry_persistence(
                event_bus=self.event_bus,
                knowledge_base=knowledge_base
            )
            self.logger.info(f"Subscribed telemetry persistence handler: {subscription_id}")
            
            # Subscribe telemetry logging handler for monitoring visibility
            async def telemetry_logger(event):
                """Log telemetry events for monitoring visibility."""
                try:
                    system_state = event.system_state
                    metrics_summary = {name: metric.value for name, metric in system_state.metrics.items()}
                    self.logger.info(f"TELEMETRY [{system_state.system_id}]: {system_state.health_status.value} - {metrics_summary}")
                except Exception as e:
                    self.logger.error(f"Error logging telemetry: {e}")
            
            logging_subscription_id = await self.event_bus.subscribe_to_telemetry(telemetry_logger)
            self.logger.info(f"Subscribed telemetry logging handler: {logging_subscription_id}")
            

            
            # Store subscriptions for cleanup
            if not hasattr(self, '_subscriptions'):
                self._subscriptions = []
            self._subscriptions.extend([subscription_id, logging_subscription_id])
            
            self._components.extend(["world_model", "knowledge_base", "learning_engine"])
            
        except Exception as e:
            self.logger.warning(f"Some digital twin components not available yet: {e}")
        
        self.logger.debug("Digital twin layer started")
    
    async def _start_control_reasoning(self) -> None:
        """Start control and reasoning layer components."""
        self.logger.debug("Starting control and reasoning layer...")
        
        try:
            from ..control_reasoning import PolarisAdaptiveController, PolarisReasoningEngine
            from ..control_reasoning import ThresholdReactiveStrategy
            from ..digital_twin import PolarisWorldModel, PolarisKnowledgeBase
            
            # Get components from DI container
            knowledge_base = self.container.resolve(PolarisKnowledgeBase)
            world_model = self.container.resolve(PolarisWorldModel)
            
            # Create reasoning engine with LLM capabilities if configured
            reasoning_engine = self._create_reasoning_engine(knowledge_base, world_model)
            self.container.register_singleton(PolarisReasoningEngine, reasoning_engine)
            
            # Create control strategies with configuration
            control_strategies = self._create_control_strategies(reasoning_engine)
            
            # Check if enhanced assessment should be enabled
            raw_config = self.configuration.get_raw_config()
            control_config = raw_config.get("control_reasoning", {})
            adaptive_config = control_config.get("adaptive_controller", {})
            enable_enhanced = adaptive_config.get("enable_enhanced_assessment", True)
            
            # Create adaptive controller
            adaptive_controller = PolarisAdaptiveController(
                control_strategies=control_strategies,
                world_model=world_model,
                knowledge_base=knowledge_base,
                event_bus=self.event_bus,
                enable_enhanced_assessment=enable_enhanced
            )
            self.container.register_singleton(PolarisAdaptiveController, adaptive_controller)
            
            # Start components
            if hasattr(adaptive_controller, 'start'):
                await adaptive_controller.start()
            if hasattr(reasoning_engine, 'start'):
                await reasoning_engine.start()
            
            # Subscribe adaptive controller to telemetry events for adaptation assessment
            try:
                adaptation_subscription_id = await self.event_bus.subscribe_to_telemetry(
                    adaptive_controller.process_telemetry
                )
                self.logger.info(f"Subscribed adaptive controller to telemetry: {adaptation_subscription_id}")
                if not hasattr(self, '_subscriptions'):
                    self._subscriptions = []
                self._subscriptions.append(adaptation_subscription_id)
            except Exception as e:
                self.logger.warning(f"Could not subscribe adaptive controller to telemetry: {e}")
            
            self._components.extend(["adaptive_controller", "reasoning_engine"])
            
        except Exception as e:
            self.logger.warning(f"Some control/reasoning components not available yet: {e}")
        
        self.logger.debug("Control and reasoning layer started")
    
    async def _start_adapters(self) -> None:
        """Start adapter layer components."""
        self.logger.debug("Starting adapter layer...")
        
        # Load and start managed system connectors
        await self.plugin_registry.load_all_connectors()
        
        # Create and start monitoring adapters for configured managed systems
        await self._start_monitoring_adapters()
        
        self._components.append("adapters")
        
        self.logger.debug("Adapter layer started")
    
    async def _start_monitoring_adapters(self) -> None:
        """Create and start monitoring adapters for configured managed systems."""
        try:
            from ..adapters.monitor_adapter import MonitorAdapter, MonitoringTarget
            from ..adapters.base_adapter import AdapterConfiguration
            
            # Get all managed system configurations
            managed_systems = self.configuration.get_all_managed_systems()
            
            if not managed_systems:
                self.logger.info("No managed systems configured, skipping monitoring adapter creation")
                return
            
            # Create monitoring targets from managed system configurations
            monitoring_targets = []
            for system_id, system_config in managed_systems.items():
                if not system_config.enabled:
                    continue
                
                # Extract monitoring configuration
                monitoring_config = system_config.monitoring_config or {}
                
                # Create monitoring target
                target = MonitoringTarget(
                    system_id=system_id,
                    connector_type=system_config.connector_type,
                    collection_interval=monitoring_config.get("collection_interval", 30),
                    enabled=True,
                    config={
                        **system_config.connection_params,
                        **monitoring_config,
                        "collection_strategy": monitoring_config.get("collection_strategy", "polling")
                    }
                )
                monitoring_targets.append(target)
                self.logger.info(f"Created monitoring target for {system_id}")
            
            if not monitoring_targets:
                self.logger.info("No enabled managed systems found, skipping monitoring adapter creation")
                return
            
            # Create monitor adapter configuration
            adapter_config = AdapterConfiguration(
                adapter_id="polaris_monitor",
                adapter_type="monitor",
                config={
                    "collection_mode": "pull",
                    "monitoring_targets": [
                        {
                            "system_id": target.system_id,
                            "connector_type": target.connector_type,
                            "collection_interval": target.collection_interval,
                            "enabled": target.enabled,
                            "config": target.config
                        }
                        for target in monitoring_targets
                    ]
                }
            )
            
            # Create and start monitor adapter
            monitor_adapter = MonitorAdapter(
                configuration=adapter_config,
                event_bus=self.event_bus,
                plugin_registry=self.plugin_registry
            )
            
            # Start the adapter
            await monitor_adapter.start()
            
            # Store reference for cleanup
            if not hasattr(self, '_adapters'):
                self._adapters = []
            self._adapters.append(monitor_adapter)
            
            self.logger.info(f"Started monitoring adapter with {len(monitoring_targets)} targets")
            
        except Exception as e:
            self.logger.error(f"Failed to start monitoring adapters: {e}", exc_info=True)
    
    async def _stop_infrastructure(self) -> None:
        """Stop infrastructure layer components."""
        self.logger.debug("Stopping infrastructure layer...")
        
        if "data_store" in self._components:
            await self.data_store.stop()
            self._components.remove("data_store")
        
        if "message_bus" in self._components:
            await self.message_bus.stop()
            self._components.remove("message_bus")
        
        self.logger.debug("Infrastructure layer stopped")
    
    async def _stop_framework_services(self) -> None:
        """Stop framework layer services."""
        self.logger.debug("Stopping framework services...")
        
        if "event_bus" in self._components:
            await self.event_bus.stop()
            self._components.remove("event_bus")
        
        if "plugin_registry" in self._components:
            await self.plugin_registry.shutdown()
            self._components.remove("plugin_registry")
        
        self.logger.debug("Framework services stopped")
    
    async def _stop_digital_twin(self) -> None:
        """Stop digital twin layer components."""
        self.logger.debug("Stopping digital twin layer...")
        
        # Unsubscribe event handlers
        if hasattr(self, '_subscriptions'):
            for subscription_id in self._subscriptions:
                try:
                    self.event_bus.unsubscribe(subscription_id)
                    self.logger.info(f"Unsubscribed event handler: {subscription_id}")
                except Exception as e:
                    self.logger.error(f"Error unsubscribing {subscription_id}: {e}")
            self._subscriptions.clear()
        
        # Stop digital twin components if they exist
        for component in ["learning_engine", "knowledge_base", "world_model"]:
            if component in self._components:
                self._components.remove(component)
        
        self.logger.debug("Digital twin layer stopped")
    
    async def _stop_control_reasoning(self) -> None:
        """Stop control and reasoning layer components."""
        self.logger.debug("Stopping control and reasoning layer...")
        
        for component in ["reasoning_engine", "adaptive_controller"]:
            if component in self._components:
                self._components.remove(component)
        
        self.logger.debug("Control and reasoning layer stopped")
    
    def _create_threshold_strategy(self):
        """Create and configure ThresholdReactiveStrategy from configuration."""
        try:
            from ..control_reasoning.threshold_reactive_strategy import (
                ThresholdReactiveStrategy, ThresholdReactiveConfig, ThresholdRule, 
                ThresholdCondition, ThresholdOperator, LogicalOperator
            )
            
            # Get control reasoning configuration
            raw_config = self.configuration.get_raw_config()
            control_config = raw_config.get("control_reasoning", {})
            threshold_config = control_config.get("threshold_reactive", {})
            
            if not threshold_config:
                self.logger.warning("No threshold_reactive configuration found, using defaults")
                return ThresholdReactiveStrategy()
            
            # Parse threshold rules
            rules = []
            rules_data = threshold_config.get("rules", [])
            
            for rule_data in rules_data:
                try:
                    # Parse conditions
                    conditions = []
                    conditions_data = rule_data.get("conditions", [])
                    
                    for condition_data in conditions_data:
                        operator_str = condition_data.get("operator", "gt")
                        operator = ThresholdOperator(operator_str)
                        
                        condition = ThresholdCondition(
                            metric_name=condition_data.get("metric_name", ""),
                            operator=operator,
                            value=condition_data.get("value", 0.0),
                            weight=condition_data.get("weight", 1.0),
                            description=condition_data.get("description")
                        )
                        conditions.append(condition)
                    
                    # Parse logical operator
                    logical_op_str = rule_data.get("logical_operator", "and")
                    logical_operator = LogicalOperator(logical_op_str)
                    
                    # Create rule
                    rule = ThresholdRule(
                        rule_id=rule_data.get("rule_id", ""),
                        name=rule_data.get("name", ""),
                        conditions=conditions,
                        logical_operator=logical_operator,
                        action_type=rule_data.get("action_type", ""),
                        action_parameters=rule_data.get("action_parameters", {}),
                        priority=rule_data.get("priority", 1),
                        cooldown_seconds=rule_data.get("cooldown_seconds", 60.0),
                        enabled=rule_data.get("enabled", True),
                        description=rule_data.get("description")
                    )
                    rules.append(rule)
                    
                except Exception as e:
                    self.logger.error(f"Error parsing threshold rule {rule_data.get('rule_id', 'unknown')}: {e}")
            
            # Create configuration
            config = ThresholdReactiveConfig(
                rules=rules,
                enable_multi_metric_evaluation=threshold_config.get("enable_multi_metric_evaluation", True),
                action_prioritization_enabled=threshold_config.get("action_prioritization_enabled", True),
                max_concurrent_actions=threshold_config.get("max_concurrent_actions", 5),
                default_cooldown_seconds=threshold_config.get("default_cooldown_seconds", 60.0),
                severity_weights=threshold_config.get("severity_weights", {
                    "critical": 3.0,
                    "high": 2.0,
                    "medium": 1.0,
                    "low": 0.5
                }),
                enable_fallback=threshold_config.get("enable_fallback", True)
            )
            
            self.logger.info(f"Created threshold strategy with {len(rules)} rules")
            return ThresholdReactiveStrategy(config)
            
        except Exception as e:
            self.logger.error(f"Error creating threshold strategy: {e}")
            self.logger.warning("Falling back to default threshold strategy")
            return ThresholdReactiveStrategy()
    
    def _create_control_strategies(self, reasoning_engine):
        """Create control strategies based on configuration."""
        strategies = []
        
        try:
            # Get control reasoning configuration
            raw_config = self.configuration.get_raw_config()
            control_config = raw_config.get("control_reasoning", {})
            adaptive_config = control_config.get("adaptive_controller", {})
            strategy_names = adaptive_config.get("control_strategies", ["threshold_reactive"])
            
            self.logger.info(f"Creating control strategies: {strategy_names}")
            
            for strategy_name in strategy_names:
                try:
                    if strategy_name == "threshold_reactive":
                        strategy = self._create_threshold_strategy()
                        strategies.append(strategy)
                        self.logger.info("Added threshold reactive strategy")
                        
                    elif strategy_name == "agentic_llm_reasoning":
                        from ..control_reasoning.llm_control_strategy import LLMControlStrategy
                        strategy = LLMControlStrategy(reasoning_engine=reasoning_engine)
                        strategies.append(strategy)
                        self.logger.info("Added LLM control strategy")
                        
                    else:
                        self.logger.warning(f"Unknown control strategy: {strategy_name}")
                        
                except Exception as e:
                    self.logger.error(f"Error creating strategy {strategy_name}: {e}")
            
            if not strategies:
                self.logger.warning("No control strategies created, adding default threshold strategy")
                strategies.append(self._create_threshold_strategy())
            
            self.logger.info(f"Created {len(strategies)} control strategies")
            return strategies
            
        except Exception as e:
            self.logger.error(f"Error creating control strategies: {e}")
            self.logger.warning("Falling back to default threshold strategy")
            return [self._create_threshold_strategy()]
    
    def _create_reasoning_engine(self, knowledge_base, world_model):
        """Create reasoning engine with appropriate strategies."""
        try:
            from ..control_reasoning.reasoning_engine import (
                PolarisReasoningEngine, StatisticalReasoningStrategy, 
                CausalReasoningStrategy, ExperienceBasedReasoningStrategy
            )
            
            # Start with basic strategies
            strategies = [
                StatisticalReasoningStrategy(knowledge_base),
                CausalReasoningStrategy(knowledge_base),
                ExperienceBasedReasoningStrategy(knowledge_base)
            ]
            
            # Try to add LLM reasoning strategy if LLM is configured
            try:
                raw_config = self.configuration.get_raw_config()
                llm_config = raw_config.get("llm", {})
                
                if llm_config.get("provider") != "mock":
                    from ..control_reasoning.agentic_llm_reasoning_strategy import AgenticLLMReasoningStrategy
                    from ..infrastructure.llm.client import LLMClient
                    
                    # Create LLM client
                    llm_client = LLMClient(llm_config)
                    
                    # Add LLM reasoning strategy
                    llm_strategy = AgenticLLMReasoningStrategy(
                        llm_client=llm_client,
                        world_model=world_model,
                        knowledge_base=knowledge_base
                    )
                    strategies.append(llm_strategy)
                    self.logger.info("Added LLM reasoning strategy to reasoning engine")
                else:
                    self.logger.info("LLM provider is mock, skipping LLM reasoning strategy")
                    
            except Exception as e:
                self.logger.warning(f"Could not add LLM reasoning strategy: {e}")
            
            reasoning_engine = PolarisReasoningEngine(
                reasoning_strategies=strategies,
                knowledge_base=knowledge_base
            )
            
            self.logger.info(f"Created reasoning engine with {len(strategies)} strategies")
            return reasoning_engine
            
        except Exception as e:
            self.logger.error(f"Error creating reasoning engine: {e}")
            # Fallback to basic reasoning engine
            from ..control_reasoning.reasoning_engine import PolarisReasoningEngine
            return PolarisReasoningEngine(knowledge_base=knowledge_base)
    
    async def _stop_adapters(self) -> None:
        """Stop adapter layer components."""
        self.logger.debug("Stopping adapter layer...")
        
        # Stop monitoring adapters
        if hasattr(self, '_adapters'):
            for adapter in self._adapters:
                try:
                    await adapter.stop()
                    self.logger.info(f"Stopped adapter {adapter.adapter_id}")
                except Exception as e:
                    self.logger.error(f"Error stopping adapter {adapter.adapter_id}: {e}")
            self._adapters.clear()
        
        if "adapters" in self._components:
            await self.plugin_registry.unload_all_connectors()
            self._components.remove("adapters")
        
        self.logger.debug("Adapter layer stopped")
    
    async def _cleanup_on_failure(self) -> None:
        """Clean up resources when startup fails."""
        self.logger.debug("Cleaning up after startup failure...")
        
        # Try to stop any components that were started
        try:
            await self.stop()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")


# Factory function for creating a configured POLARIS framework
async def create_polaris_framework(config_path: Optional[str] = None) -> PolarisFramework:
    """
    Factory function to create a fully configured POLARIS framework instance.
    
    Args:
        config_path: Optional path to configuration file
        
    Returns:
        PolarisFramework: Configured framework instance
    """
    from .configuration import ConfigurationBuilder
    
    # Create DI container
    container = DIContainer()
    
    # Load configuration
    config_builder = ConfigurationBuilder()
    if config_path:
        config_builder.add_yaml_source(config_path)
    config_builder.add_environment_source("POLARIS_")
    
    configuration = config_builder.build()
    
    # Register core services in DI container
    container.register_singleton(PolarisConfiguration, configuration)
    
    # Create and register other components
    # Note: Actual implementations will be created in subsequent tasks
    
    # For now, create a basic framework instance
    framework = PolarisFramework(
        container=container,
        configuration=configuration,
        message_bus=None,  # Will be created in infrastructure tasks
        data_store=None,   # Will be created in infrastructure tasks
        plugin_registry=None,  # Will be created in plugin management tasks
        event_bus=None     # Will be created in event system tasks
    )
    
    return framework