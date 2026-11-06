import pytest
from unittest.mock import MagicMock, patch
from plugins.sys_info.main import Plugin
from core.event_bus import event_bus

@pytest.mark.asyncio
async def test_sys_info_update_stats():
    # Mock psutil
    mock_cpu_times1 = MagicMock(idle=100.0)
    mock_cpu_times1.__iter__.return_type = iter([100.0, 50.0]) # sum is 150.0
    
    mock_cpu_times2 = MagicMock(idle=110.0)
    mock_cpu_times2.__iter__.return_type = iter([110.0, 70.0]) # sum is 180.0
    
    # Let sum(mock_cpu_times) return total times
    # In python, mock sum by returning specific list sum
    
    mock_virtual_memory = MagicMock(
        percent=45.2,
        used=8.2 * (1024**3),
        total=16.0 * (1024**3)
    )

    # We patch psutil
    with patch("plugins.sys_info.main.psutil") as mock_psutil:
        # We need sum(self._last_cpu_times) to work
        # Let's mock cpu_times() to return a tuple-like object
        class MockCpuTimes:
            def __init__(self, idle, user, system):
                self.idle = idle
                self.user = user
                self.system = system
            def __iter__(self):
                return iter([self.idle, self.user, self.system])
        
        times1 = MockCpuTimes(100.0, 50.0, 10.0) # total = 160.0
        times2 = MockCpuTimes(110.0, 60.0, 20.0) # total = 190.0
        
        # mock_psutil.cpu_times returns times1 on first call, times2 on second call
        mock_psutil.cpu_times.side_effect = [times1, times2]
        mock_psutil.virtual_memory.return_value = mock_virtual_memory

        # Initialize plugin
        plugin = Plugin("sys_info")
        
        # Test state emission on update_stats
        emitted_states = []
        async def on_state_changed(payload):
            if payload.get("plugin_id") == "sys_info":
                emitted_states.append(payload["state"])
                
        event_bus.subscribe("plugin_state_changed", on_state_changed)
        try:
            await plugin._update_stats()
        finally:
            event_bus.unsubscribe("plugin_state_changed", on_state_changed)
            
        assert len(emitted_states) == 1
        state = emitted_states[0]
        
        # cpu delta total = 190 - 160 = 30
        # cpu delta idle = 110 - 100 = 10
        # cpu percent = (1.0 - 10/30) * 100 = 66.6666%
        assert abs(state["cpu_load"] - 66.6666) < 0.1
        assert state["ram_percent"] == 45.2
        assert state["ram_used_gb"] == 8.2
        assert state["ram_total_gb"] == 16.0
