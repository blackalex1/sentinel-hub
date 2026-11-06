import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from plugins.sentinel_music.main import Plugin
from plugins.sentinel_music.client import SentinelClient
from core.event_bus import event_bus

@pytest.fixture
def sentinel_plugin():
    plugin = Plugin("sentinel_music")
    # Mock database config / secret methods on BasePlugin
    plugin.get_config = MagicMock(return_value={"server_url": "http://127.0.0.1:8000"})
    plugin.save_config = MagicMock()
    plugin._secrets = {}
    plugin.get_secret = MagicMock(side_effect=lambda k, d=None: plugin._secrets.get(k, d))
    plugin.set_secret = MagicMock(side_effect=lambda k, v: plugin._secrets.update({k: v}))
    return plugin

@pytest.mark.asyncio
async def test_sentinel_login_and_save_settings(sentinel_plugin):
    plugin = sentinel_plugin

    # Mock client methods
    with patch.object(plugin.client, "login", new_callable=AsyncMock) as mock_login, \
         patch.object(plugin.client, "start_ws") as mock_start_ws, \
         patch.object(plugin.client, "disconnect_ws", new_callable=AsyncMock) as mock_disconnect_ws:

        mock_login.return_value = (True, "test_token_123", "alice", None)

        validation_events = []
        async def on_event(payload):
            if payload.get("plugin_id") == "sentinel_music" and payload.get("event") == "settings_validation_result":
                validation_events.append(payload["data"])

        event_bus.subscribe("plugin_custom_event", on_event)
        try:
            await plugin.handle_command("save_settings", {
                "server_url": "http://192.168.1.50:8000",
                "username": "alice",
                "password": "secretpassword"
            })
        finally:
            event_bus.unsubscribe("plugin_custom_event", on_event)

        # Проверяем сохранение токена и конфигурации
        assert plugin.get_secret("SENTINEL_TOKEN") == "test_token_123"
        plugin.save_config.assert_called_with({"server_url": "http://192.168.1.50:8000"})
        assert plugin.is_authenticated is True
        assert plugin.auth_username == "alice"
        assert len(validation_events) == 1
        assert validation_events[0]["success"] is True
        mock_start_ws.assert_called_once()

@pytest.mark.asyncio
async def test_sentinel_state_broadcast(sentinel_plugin):
    plugin = sentinel_plugin
    state_events = []

    async def on_state(payload):
        if payload.get("plugin_id") == "sentinel_music":
            state_events.append(payload["state"])

    event_bus.subscribe("plugin_state_changed", on_state)
    try:
        # Симулируем получение обновления устройств через Sentinel Connect
        sample_devices = [
            {
                "id": "station_kitchen",
                "name": "Яндекс Станция (Кухня)",
                "can_play": True,
                "is_playing": True,
                "current_track": {
                    "id": 42,
                    "title": "Bohemian Rhapsody",
                    "artist": "Queen",
                    "duration": 354.0
                },
                "position_ms": 60000,
                "duration_ms": 354000,
                "volume": 0.75
            }
        ]

        with patch.object(plugin.client, "get_lyrics", new_callable=AsyncMock) as mock_lyrics:
            mock_lyrics.return_value = [{"time": 1000, "text": "Is this the real life?"}]
            await plugin._on_devices_update(sample_devices)
            # Даем фоновой таске загрузки текстов выполниться
            await asyncio.sleep(0.05)

    finally:
        event_bus.unsubscribe("plugin_state_changed", on_state)

    assert len(state_events) > 0
    latest_state = state_events[-1]
    assert len(latest_state["devices"]) == 1
    dev = latest_state["devices"][0]
    assert dev["id"] == "station_kitchen"
    assert dev["title"] == "Bohemian Rhapsody"
    assert dev["artist"] == "Queen"
    assert dev["playing"] is True
    assert dev["progress"] == 60.0
    assert dev["duration"] == 354.0
    assert dev["volume"] == 75
    assert dev["cover"] == "http://127.0.0.1:8000/covers/42?size=300"
    assert len(dev["timings"]) == 1
    assert dev["timings"][0]["text"] == "Is this the real life?"

@pytest.mark.asyncio
async def test_sentinel_playback_commands(sentinel_plugin):
    plugin = sentinel_plugin
    plugin.devices = {
        "desktop_pc": {
            "id": "desktop_pc",
            "name": "Рабочий ПК",
            "is_playing": False,
            "volume": 0.5
        }
    }

    with patch.object(plugin.client, "send_command", new_callable=AsyncMock) as mock_send:
        # Play / Pause
        await plugin.handle_command("play_pause", "desktop_pc")
        mock_send.assert_called_with("desktop_pc", "TOGGLE_PLAY")

        # Next track
        await plugin.handle_command("next_track", "desktop_pc")
        mock_send.assert_called_with("desktop_pc", "NEXT")

        # Prev track
        await plugin.handle_command("prev_track", "desktop_pc")
        mock_send.assert_called_with("desktop_pc", "PREV")

        # Seek to 42.5 seconds
        await plugin.handle_command("seek:42.5", "desktop_pc")
        mock_send.assert_called_with("desktop_pc", "SEEK", {"position_ms": 42500})

        # Set volume to 80%
        await plugin.handle_command("set_volume:80", "desktop_pc")
        mock_send.assert_called_with("desktop_pc", "SET_VOLUME", {"volume": 0.8})

@pytest.mark.asyncio
async def test_sentinel_logout(sentinel_plugin):
    plugin = sentinel_plugin
    plugin.set_secret("SENTINEL_TOKEN", "active_tok")
    plugin.is_authenticated = True
    plugin.auth_username = "alice"

    with patch.object(plugin.client, "disconnect_ws", new_callable=AsyncMock) as mock_disconnect:
        await plugin.handle_command("logout", {})

        assert plugin.get_secret("SENTINEL_TOKEN") == ""
        assert plugin.is_authenticated is False
        assert plugin.auth_username is None
        mock_disconnect.assert_called_once()
