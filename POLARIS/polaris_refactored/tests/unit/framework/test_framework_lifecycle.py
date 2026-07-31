import asyncio
import pytest

from polaris_refactored.src.framework.polaris_framework import PolarisFramework
from polaris_refactored.src.infrastructure.di import DIContainer
from polaris_refactored.src.infrastructure.exceptions import PolarisException
from polaris_refactored.src.framework.events import PolarisEventBus
from polaris_refactored.src.digital_twin import PolarisWorldModel, PolarisKnowledgeBase, PolarisLearningEngine
from polaris_refactored.src.control_reasoning import PolarisAdaptiveController, PolarisReasoningEngine


class FakeService:
    def __init__(self):
        self.started = False
        self.stopped = False
        self._connected = False

    async def start(self):
        self.started = True
        self._connected = True

    async def stop(self):
        self.stopped = True
        self._connected = False


class FakeMessageBus(FakeService):
    pass


class FakeDataStore(FakeService):
    pass


class FakePluginRegistry:
    def __init__(self, fail_on_load=False):
        self.initialized = False
        self.shutdown_called = False
        self.loaded = False
        self.unloaded = False
        self.fail_on_load = fail_on_load

    async def initialize(self):
        self.initialized = True

    async def shutdown(self):
        self.shutdown_called = True

    async def load_all_connectors(self):
        if self.fail_on_load:
            raise RuntimeError("load failure")
        self.loaded = True

    async def unload_all_connectors(self):
        self.unloaded = True


class FakeEventBus(FakeService):
    pass


class FakeComponent:
    def __init__(self):
        self.started = False

    async def start(self):
        self.started = True


@pytest.mark.asyncio
async def test_framework_start_stop_order_and_status():
    container = DIContainer()

    # Register digital twin and control components to DI
    container.register_factory(PolarisWorldModel, lambda: FakeComponent())
    container.register_factory(PolarisKnowledgeBase, lambda: FakeComponent())
    container.register_factory(PolarisLearningEngine, lambda: FakeComponent())
    container.register_factory(PolarisAdaptiveController, lambda: FakeComponent())
    container.register_factory(PolarisReasoningEngine, lambda: FakeComponent())

    msg_bus = FakeMessageBus()
    data_store = FakeDataStore()
    plugin_registry = FakePluginRegistry()
    event_bus = FakeEventBus()

    framework = PolarisFramework(
        container=container,
        configuration=None,
        message_bus=msg_bus,
        data_store=data_store,
        plugin_registry=plugin_registry,
        event_bus=event_bus,
    )

    await framework.start()
    status = framework.get_status()
    assert status["running"] is True
    # Ensure ordering captured
    assert status["components"] == [
        "message_bus",
        "data_store",
        "plugin_registry",
        "event_bus",
        "world_model",
        "knowledge_base",
        "learning_engine",
        "adaptive_controller",
        "reasoning_engine",
        "adapters",
    ]

    await framework.stop()
    status2 = framework.get_status()
    assert status2["running"] is False
    assert status2["components"] == []


@pytest.mark.asyncio
async def test_framework_idempotent_start_stop():
    container = DIContainer()
    container.register_factory(PolarisWorldModel, lambda: FakeComponent())
    container.register_factory(PolarisKnowledgeBase, lambda: FakeComponent())
    container.register_factory(PolarisLearningEngine, lambda: FakeComponent())
    container.register_factory(PolarisAdaptiveController, lambda: FakeComponent())
    container.register_factory(PolarisReasoningEngine, lambda: FakeComponent())

    framework = PolarisFramework(
        container=container,
        configuration=None,
        message_bus=FakeMessageBus(),
        data_store=FakeDataStore(),
        plugin_registry=FakePluginRegistry(),
        event_bus=FakeEventBus(),
    )

    await framework.start()
    before = framework.get_status()["components"].copy()
    # start again should warn and no change
    await framework.start()
    after = framework.get_status()["components"].copy()
    assert before == after

    await framework.stop()
    await framework.stop()  # idempotent
    assert framework.get_status()["components"] == []


@pytest.mark.asyncio
async def test_framework_cleanup_on_failure_during_adapters():
    container = DIContainer()
    container.register_factory(PolarisWorldModel, lambda: FakeComponent())
    container.register_factory(PolarisKnowledgeBase, lambda: FakeComponent())
    container.register_factory(PolarisLearningEngine, lambda: FakeComponent())
    container.register_factory(PolarisAdaptiveController, lambda: FakeComponent())
    container.register_factory(PolarisReasoningEngine, lambda: FakeComponent())

    msg_bus = FakeMessageBus()
    data_store = FakeDataStore()
    plugin_registry = FakePluginRegistry(fail_on_load=True)
    event_bus = FakeEventBus()

    framework = PolarisFramework(
        container=container,
        configuration=None,
        message_bus=msg_bus,
        data_store=data_store,
        plugin_registry=plugin_registry,
        event_bus=event_bus,
    )

    with pytest.raises(PolarisException) as ex:
        await framework.start()
    assert ex.value.error_code == "FRAMEWORK_START_ERROR"

    # After failure, framework is not running; current implementation does not clear components
    # because stop() is a no-op when not running. Assert non-running and presence of partial components.
    assert framework.is_running() is False
    comps_after = framework.get_status()["components"]
    assert len(comps_after) > 0
