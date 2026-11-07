import pytest
import asyncio
import time
import os
import json
from unittest.mock import MagicMock, AsyncMock, patch
from plugins.yandex_station.worker import DeviceWorker
from plugins.pc_media.media_scanner import main_loop
from plugins.system_stats.sensor_helper import SensorHelper

@pytest.mark.asyncio
async def test_yandex_station_worker_no_orphans_on_failure():
    # Create mock plugin class to handle getattr and stop event values
    class MockPlugin:
        def __init__(self):
            self.cmd_queues = {}
            self.states = {}
            self.log = MagicMock()
            self.broadcaster = AsyncMock()
            self.auth = AsyncMock()
            self._stop_event_value = [False, True]
            
        @property
        def _stop_event(self):
            return self._stop_event_value.pop(0) if self._stop_event_value else True

    mock_plugin = MockPlugin()
    worker = DeviceWorker(mock_plugin, "device_123")
    
    # Mock loops
    # Loop 1: control loop runs forever until cancelled
    async def mock_control_loop():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            mock_control_loop.cancelled = True
            raise
            
    mock_control_loop.cancelled = False
    worker._control_loop = mock_control_loop
    
    # Loop 2: monitor loop raises an exception after 0.05 seconds
    async def mock_monitor_loop():
        await asyncio.sleep(0.05)
        raise ValueError("Simulated network failure")
        
    worker._monitor_loop = mock_monitor_loop
    
    # Start the worker task
    worker.start()
    
    # Wait for the worker to run and the exception to occur
    await asyncio.sleep(0.2)
    
    # Verify that the control loop was cancelled and cleaned up
    assert mock_control_loop.cancelled is True
    
    # Clean up the worker tasks
    for t in worker._tasks:
        t.cancel()
    await asyncio.gather(*worker._tasks, return_exceptions=True)


@pytest.mark.asyncio
@patch('plugins.pc_media.media_scanner.SessionManager')
@patch('plugins.pc_media.media_scanner.SystemVolume')
@patch('psutil.Process')
async def test_media_scanner_memory_limit_exceeded(mock_process, mock_volume, mock_session_manager):
    # Set up mock process memory usage to be > 150 MB (e.g. 160 MB)
    mock_proc_instance = MagicMock()
    mock_proc_instance.memory_info.return_value.rss = 160 * 1024 * 1024
    mock_process.return_value = mock_proc_instance
    
    # Mock system volume and sessions
    mock_vol_instance = MagicMock()
    mock_vol_instance.get_info.return_value = (50, False)
    mock_volume.return_value = mock_vol_instance
    
    mock_manager = MagicMock()
    mock_session_manager.request_async = AsyncMock(return_value=mock_manager)
    
    # Mock time to simulate 31 seconds passing on the first loop iteration
    time_values = [0, 31, 32, 33]
    
    with patch('time.time', side_effect=lambda: time_values.pop(0) if time_values else 100):
        with patch('builtins.print') as mock_print:
            # Run the main loop. Since memory is high, it should break and exit immediately.
            await asyncio.wait_for(main_loop(), timeout=1.0)
            
            # Assert that the print was called indicating memory threshold was exceeded
            printed_msgs = [call[0][0] for call in mock_print.call_args_list]
            assert any("Memory threshold exceeded" in msg for msg in printed_msgs)


@patch('plugins.system_stats.sensor_helper.is_process_running')
@patch('plugins.system_stats.sensor_helper.init_clr_and_dll')
@patch('mmap.mmap')
@patch('gc.collect')
@patch('time.sleep')
def test_sensor_helper_gc_collect(mock_sleep, mock_gc_collect, mock_mmap, mock_init_clr, mock_is_running):
    # Mock dll init and shmem
    mock_init_clr.return_value = None
    
    mock_shmem = MagicMock()
    mock_mmap.return_value = mock_shmem
    
    # Mock process running to run exactly once and then exit
    mock_is_running.side_effect = [True, False]
    
    helper = SensorHelper(parent_pid=123)
    
    with patch('builtins.open', MagicMock()):
        helper.run("dummy_dll_path")
    
    # Verify gc.collect() was called
    assert mock_gc_collect.called
