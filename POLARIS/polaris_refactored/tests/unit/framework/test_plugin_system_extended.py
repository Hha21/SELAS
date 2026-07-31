import asyncio
from pathlib import Path
import textwrap
import pytest

from polaris_refactored.src.framework.plugin_management.plugin_registry import PolarisPluginRegistry
from polaris_refactored.src.framework.plugin_management.plugin_discovery import PluginDiscovery
from polaris_refactored.src.framework.plugin_management.plugin_descriptor import PluginDescriptor


PLUGIN_YAML = """
name: test_connector
version: 1.0.0
connector_class: TestConnector
module: connector
"""

# Minimal valid ManagedSystemConnector implementation as a plugin
CONNECTOR_PY = textwrap.dedent(
    """
    import asyncio
    from polaris_refactored.src.domain.interfaces import ManagedSystemConnector
    from polaris_refactored.src.domain.models import SystemState, MetricValue, ExecutionResult, ExecutionStatus, HealthStatus
    from datetime import datetime, timezone

    class TestConnector(ManagedSystemConnector):
        async def connect(self) -> bool:
            return True
        async def disconnect(self) -> bool:
            return True
        async def get_system_id(self) -> str:
            return "test_connector"
        async def collect_metrics(self):
            return {}
        async def get_system_state(self) -> SystemState:
            return SystemState(
                system_id="test_connector",
                timestamp=datetime.now(timezone.utc),
                metrics={"cpu": MetricValue("cpu", 0.5)},
                health_status=HealthStatus.HEALTHY,
            )
        async def execute_action(self, action):
            return ExecutionResult(action_id=action.action_id, status=ExecutionStatus.SUCCESS, result_data={})
        async def validate_action(self, action) -> bool:
            return True
        async def get_supported_actions(self):
            return ["scale", "restart"]
    """
)


@pytest.mark.asyncio
async def test_plugin_registry_initialize_and_load_connector(tmp_path: Path, monkeypatch):
    # Create a plugin directory
    plugin_dir = tmp_path / "plugins" / "test_connector"
    plugin_dir.mkdir(parents=True)

    # Write metadata and connector code
    (plugin_dir / "plugin.yaml").write_text(PLUGIN_YAML, encoding="utf-8")
    (plugin_dir / "connector.py").write_text(CONNECTOR_PY, encoding="utf-8")

    reg = PolarisPluginRegistry()
    # Initialize with search path
    await reg.initialize(search_paths=[plugin_dir.parent], enable_hot_reload=False)

    # Should have discovered descriptor
    descs = reg.get_plugin_descriptors()
    assert "test_connector" in descs and descs["test_connector"].is_valid

    # Load connector instance
    conn = reg.load_managed_system_connector("test_connector")
    assert conn is not None
    assert await conn.connect() is True
    assert "scale" in await conn.get_supported_actions()

    await reg.unload_all_connectors()
    await reg.shutdown()


def test_plugin_discovery_invalid_metadata(tmp_path: Path):
    # Missing required fields makes descriptor invalid
    plugin_dir = tmp_path / "plugins" / "bad"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yaml").write_text("name: bad\n", encoding="utf-8")
    (plugin_dir / "connector.py").write_text("# no class here\n", encoding="utf-8")

    disc = PluginDiscovery()
    results = disc.discover_managed_system_plugins([plugin_dir.parent])
    # Either no plugin or invalid descriptor
    assert all(isinstance(p, PluginDescriptor) for p in results)
    # We don't guarantee discovery if validation fails, so allow either empty or invalid
    if results:
        # If present, it should be marked invalid
        assert any(not p.is_valid for p in results)
