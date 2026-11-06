import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from plugins.proxmox_sentinel.main import Plugin
from core.event_bus import event_bus

@pytest.fixture
def proxmox_plugin():
    plugin = Plugin("proxmox_sentinel")
    plugin.get_config = MagicMock(return_value={"server_url": "https://192.168.1.89:8443"})
    plugin.save_config = MagicMock()
    plugin._secrets = {}
    plugin.get_secret = MagicMock(side_effect=lambda k, d="": plugin._secrets.get(k, d))
    plugin.set_secret = MagicMock(side_effect=lambda k, v: plugin._secrets.update({k: v}))
    return plugin

@pytest.mark.asyncio
async def test_proxmox_sentinel_startup(proxmox_plugin):
    plugin = proxmox_plugin
    with patch.object(plugin, "emit_state", new_callable=AsyncMock) as mock_emit:
        await plugin.on_start()
        mock_emit.assert_called_once()
        state = mock_emit.call_args[0][0]
        assert state["active"] is True
        assert state["server_url"] == "https://192.168.1.89:8443"

@pytest.mark.asyncio
async def test_proxmox_sentinel_save_settings(proxmox_plugin):
    plugin = proxmox_plugin
    with patch.object(plugin, "emit_state", new_callable=AsyncMock) as mock_emit, \
         patch.object(plugin, "emit_event", new_callable=AsyncMock) as mock_emit_event:
        
        await plugin.handle_command("save_settings", {
            "server_url": "192.168.1.99:8443",
            "token": "my_secret_bearer_token_12345"
        })

        assert plugin.server_url == "https://192.168.1.99:8443"
        assert plugin.token == "my_secret_bearer_token_12345"
        plugin.save_config.assert_called_with({"server_url": "https://192.168.1.99:8443"})
        mock_emit.assert_called()
        state = mock_emit.call_args[0][0]
        assert state["configured"] is True
        mock_emit_event.assert_called_with("settings_validation_result", {
            "success": True,
            "message": "Настройки Proxmox Sentinel успешно сохранены"
        })

@pytest.mark.asyncio
async def test_proxmox_sentinel_clear_alerts(proxmox_plugin):
    plugin = proxmox_plugin
    with patch.object(plugin, "emit_event", new_callable=AsyncMock) as mock_emit_event:
        await plugin.handle_command("clear_alerts", {})
        mock_emit_event.assert_called_once_with("proxmox_clear_alerts", {})
