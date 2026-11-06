import pytest
from unittest.mock import MagicMock, patch
from plugins.app_launcher.main import Plugin
from core.event_bus import event_bus

@pytest.mark.asyncio
async def test_app_launcher_emit_state():
    plugin = Plugin("app_launcher")
    
    # Mock configuration return value
    plugin.get_config = MagicMock(return_value={
        "widgets": [
            {
                "type": "button_group",
                "buttons": [
                    {"label": "Browser", "action": "launch", "data": "chrome"},
                    {"label": "Settings", "action": "system", "data": "control"}
                ]
            }
        ]
    })

    emitted_states = []
    async def on_state_changed(payload):
        if payload.get("plugin_id") == "app_launcher":
            emitted_states.append(payload["state"])

    event_bus.subscribe("plugin_state_changed", on_state_changed)
    try:
        await plugin._emit_launcher_state()
    finally:
        event_bus.unsubscribe("plugin_state_changed", on_state_changed)

    assert len(emitted_states) == 1
    buttons = emitted_states[0]["buttons"]
    assert len(buttons) == 2
    assert buttons[0]["label"] == "Browser"
    assert buttons[1]["label"] == "Settings"

@pytest.mark.asyncio
async def test_app_launcher_launch_command():
    plugin = Plugin("app_launcher")
    
    plugin.get_config = MagicMock(return_value={
        "widgets": [
            {
                "type": "button_group",
                "buttons": [
                    {"label": "Notepad", "action": "launch", "data": "notepad.exe"}
                ]
            }
        ]
    })

    with patch("plugins.app_launcher.main.asyncio.to_thread") as mock_to_thread:
        # Send launch command for notepad.exe
        await plugin.handle_command("launch", "notepad.exe")
        
        # Verify that to_thread was called to run launch target asynchronously
        mock_to_thread.assert_called_once()
        called_func = mock_to_thread.call_args[0][0]
        called_arg = mock_to_thread.call_args[0][1]
        
        # We expect it to call the launch app helper with notepad.exe
        assert called_func == plugin._launch_app
        assert called_arg == "notepad.exe"
