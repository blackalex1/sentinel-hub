import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from plugins.system_stats.main import Plugin
from core.event_bus import event_bus

@pytest.mark.asyncio
async def test_system_stats_update_and_emit():
    class MockCpuTimes:
        def __init__(self, idle, user):
            self.idle = idle
            self.user = user
        def __iter__(self):
            return iter([self.idle, self.user])

    times1 = MockCpuTimes(100.0, 50.0) # total = 150.0
    times2 = MockCpuTimes(110.0, 70.0) # total = 180.0 (busy delta = 20, total delta = 30 -> 66.66%)

    mock_virtual_memory = MagicMock(
        percent=55.0,
        used=8.8 * (1024**3),
        total=16.0 * (1024**3)
    )

    with patch("plugins.system_stats.main.psutil") as mock_psutil, \
         patch("plugins.system_stats.main.get_afterburner_stats") as mock_ab, \
         patch("plugins.system_stats.main.get_elevation_manager") as mock_em:

        mock_psutil.cpu_times.side_effect = [times1, times2]
        mock_psutil.virtual_memory.return_value = mock_virtual_memory

        # Mock Afterburner stats
        mock_ab.return_value = {
            "gpu_temp": 65.0,
            "gpu_load": 40.0,
            "cpu_temp": 55.0,
            "gpu_name": "NVIDIA GTX 1080"
        }

        # Mock Elevation Manager
        mock_helper = AsyncMock()
        mock_helper.get_stats.return_value = {}
        mock_em.return_value = mock_helper

        # Initialize plugin
        plugin = Plugin("system_stats")
        
        # Override get_config to return CPU and RAM as enabled
        plugin.get_config = MagicMock(return_value={
            "enabled_sensors": {
                "cpu": True,
                "ram": True,
                "cpu_temp": True,
                "gpu_load": True,
                "gpu_temp": True
            }
        })

        emitted_states = []
        async def on_state_changed(payload):
            if payload.get("plugin_id") == "system_stats":
                emitted_states.append(payload["state"])

        event_bus.subscribe("plugin_state_changed", on_state_changed)
        try:
            await plugin._update_and_emit()
        finally:
            event_bus.unsubscribe("plugin_state_changed", on_state_changed)

        assert len(emitted_states) == 1
        state = emitted_states[0]

        assert abs(state["cpu"] - 66.66) < 0.1
        assert state["ram_percent"] == 55.0
        assert state["gpu_temp"] == 65.0
        assert state["gpu_load"] == 40.0
        assert state["cpu_temp"] == 55.0
        assert state["gpu_name"] == "NVIDIA GTX 1080"
