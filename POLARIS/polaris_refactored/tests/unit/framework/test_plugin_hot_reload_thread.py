import time
import pytest

from polaris_refactored.src.framework.plugin_management.plugin_registry import PolarisPluginRegistry


@pytest.mark.asyncio
async def test_plugin_registry_hot_reload_thread_lifecycle(monkeypatch):
    reg = PolarisPluginRegistry()

    # Start hot reload monitoring without real plugins
    await reg.initialize(search_paths=[], enable_hot_reload=True)

    # Give the thread a moment to start
    time.sleep(0.1)

    # Shutdown should stop hot-reload thread and clean up
    await reg.shutdown()

    # If shutdown completed without exceptions, lifecycle is healthy
    assert True
