import pytest
import os
import shutil
from unittest.mock import MagicMock, patch, AsyncMock
from plugins.pc_media.main import Plugin
from core.event_bus import event_bus

@pytest.mark.asyncio
async def test_pc_media_send_cover():
    plugin = Plugin("pc_media")
    
    with patch("plugins.pc_media.main.os.path.exists") as mock_exists, \
         patch("shutil.copy2") as mock_copy, \
         patch("network.discovery.DiscoveryManager") as mock_dm:
         
        # Simulate that cover.jpg exists
        mock_exists.return_value = True
        
        # Mock DiscoveryManager to return local IP
        mock_dm_instance = MagicMock()
        mock_dm_instance.get_local_ip.return_value = "192.168.1.100"
        mock_dm.return_value = mock_dm_instance

        # Subscribe to custom event and state changed event
        custom_events = []
        state_changes = []

        async def on_custom_event(payload):
            if payload.get("plugin_id") == "pc_media":
                custom_events.append(payload)

        async def on_state_changed(payload):
            if payload.get("plugin_id") == "pc_media":
                state_changes.append(payload["state"])

        event_bus.subscribe("plugin_custom_event", on_custom_event)
        event_bus.subscribe("plugin_state_changed", on_state_changed)

        try:
            # We override i18n to avoid loading translation managers
            plugin.i18n = MagicMock(return_value="My Computer")
            
            await plugin._send_cover_from_file("Awesome Track")
        finally:
            event_bus.unsubscribe("plugin_custom_event", on_custom_event)
            event_bus.unsubscribe("plugin_state_changed", on_state_changed)

        # Verify cover copy was triggered
        mock_copy.assert_called_once()
        
        # Verify cover URL structure
        assert len(custom_events) == 1
        cover_url = custom_events[0]["data"]["cover"]
        assert cover_url.startswith("https://192.168.1.100:5000/static/cover.jpg?t=")
        
        assert len(state_changes) == 1
        assert state_changes[0]["cover"] == cover_url

@pytest.mark.asyncio
async def test_pc_media_volume_commands():
    plugin = Plugin("pc_media")
    
    # Mock VolumeManager methods
    plugin.volume_manager = MagicMock()
    
    # Test set_volume
    await plugin.handle_command("set_volume:75", {})
    plugin.volume_manager.set_volume.assert_called_once_with(75)
    
    # Test toggle_mute
    plugin._media_info["mute"] = False
    await plugin.handle_command("toggle_mute", {})
    plugin.volume_manager.set_mute.assert_called_once_with(True)
