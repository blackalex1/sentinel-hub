import pytest
from unittest.mock import MagicMock, patch
from plugins.pc_system.main import Plugin

@pytest.mark.asyncio
async def test_pc_system_lock():
    plugin = Plugin("pc_system")
    with patch("plugins.pc_system.main.ctypes") as mock_ctypes:
        await plugin.handle_command("lock", {})
        mock_ctypes.windll.user32.LockWorkStation.assert_called_once()

@pytest.mark.asyncio
async def test_pc_system_sleep():
    plugin = Plugin("pc_system")
    with patch("plugins.pc_system.main.ctypes") as mock_ctypes:
        await plugin.handle_command("sleep", {})
        mock_ctypes.windll.powrprof.SetSuspendState.assert_called_once_with(0, 0, 0)

@pytest.mark.asyncio
async def test_pc_system_sleep_fallback():
    plugin = Plugin("pc_system")
    with patch("plugins.pc_system.main.ctypes") as mock_ctypes, \
         patch("plugins.pc_system.main.subprocess") as mock_subproc:
        
        # Raise error in ctypes call to trigger fallback
        mock_ctypes.windll.powrprof.SetSuspendState.side_effect = Exception("API error")
        
        await plugin.handle_command("sleep", {})
        mock_subproc.Popen.assert_called_once()
        args = mock_subproc.Popen.call_args[0][0]
        assert "rundll32.exe" in args
        assert "powrprof.dll,SetSuspendState" in args

@pytest.mark.asyncio
async def test_pc_system_shutdown_and_restart():
    plugin = Plugin("pc_system")
    with patch("plugins.pc_system.main.subprocess") as mock_subproc:
        await plugin.handle_command("shutdown", {})
        mock_subproc.Popen.assert_called_once()
        args = mock_subproc.Popen.call_args[0][0]
        assert "shutdown" in args
        assert "/s" in args

    with patch("plugins.pc_system.main.subprocess") as mock_subproc:
        await plugin.handle_command("restart", {})
        mock_subproc.Popen.assert_called_once()
        args = mock_subproc.Popen.call_args[0][0]
        assert "shutdown" in args
        assert "/r" in args
