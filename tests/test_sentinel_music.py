import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from plugins.sentinel_music.main import Plugin
from plugins.sentinel_music.client import (
    SentinelClient,
    parse_token_input,
    normalize_server_url
)
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

def test_parse_token_input():
    # 1. Plain token
    tok, url, user = parse_token_input("my_test_token_123")
    assert tok == "my_test_token_123"
    assert url is None
    assert user is None

    # 2. Bearer prefix (case insensitive)
    tok, _, _ = parse_token_input("Bearer enc:v1:abc123xyz")
    assert tok == "enc:v1:abc123xyz"
    tok, _, _ = parse_token_input("bearer simple_token")
    assert tok == "simple_token"

    # 3. Quoted token
    tok, _, _ = parse_token_input('"enc:v1:quoted_token"')
    assert tok == "enc:v1:quoted_token"

    # 4. URL-encoded token
    tok, _, _ = parse_token_input("enc%3Av1%3Aurl_encoded_token")
    assert tok == "enc:v1:url_encoded_token"

    # 5. Full JSON QR payload
    qr_json = '{"url":"https://192.168.1.97:8000","token":"enc:v1:payload_token","username":"black"}'
    tok, url, user = parse_token_input(qr_json)
    assert tok == "enc:v1:payload_token"
    assert url == "https://192.168.1.97:8000"
    assert user == "black"

    # 6. JSON with Bearer inside
    qr_json_bearer = '{"url":"https://192.168.1.97:8000","token":"Bearer enc:v1:bearer_inside","username":"alex"}'
    tok, url, user = parse_token_input(qr_json_bearer)
    assert tok == "enc:v1:bearer_inside"
    assert user == "alex"

def test_normalize_server_url():
    assert normalize_server_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
    assert normalize_server_url("https://192.168.1.97:8000/") == "https://192.168.1.97:8000"
    assert normalize_server_url("https://192.168.1.97:8000/api") == "https://192.168.1.97:8000"
    assert normalize_server_url("https://192.168.1.97:8000/api/") == "https://192.168.1.97:8000"
    assert normalize_server_url("192.168.1.97:8000") == "http://192.168.1.97:8000"

@pytest.mark.asyncio
async def test_sentinel_login_and_save_settings(sentinel_plugin):
    plugin = sentinel_plugin

    with patch.object(plugin.client, "login", new_callable=AsyncMock) as mock_login, \
         patch.object(plugin.client, "start_ws") as mock_start_ws, \
         patch.object(plugin.client, "disconnect_ws", new_callable=AsyncMock):

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

        assert plugin.get_secret("SENTINEL_TOKEN") == "test_token_123"
        plugin.save_config.assert_called_with({"server_url": "http://192.168.1.50:8000"})
        assert plugin.is_authenticated is True
        assert plugin.auth_username == "alice"
        assert len(validation_events) == 1
        assert validation_events[0]["success"] is True
        mock_start_ws.assert_called_once()

@pytest.mark.asyncio
async def test_sentinel_qr_payload_save_settings(sentinel_plugin):
    plugin = sentinel_plugin

    with patch.object(plugin.client, "verify_token", new_callable=AsyncMock) as mock_verify, \
         patch.object(plugin.client, "start_ws") as mock_start_ws, \
         patch.object(plugin.client, "disconnect_ws", new_callable=AsyncMock):

        mock_verify.return_value = (True, "black", None)

        qr_json = '{"url":"https://192.168.1.97:8000","token":"Bearer enc:v1:sample_aes_gcm_token","username":"black"}'

        validation_events = []
        async def on_event(payload):
            if payload.get("plugin_id") == "sentinel_music" and payload.get("event") == "settings_validation_result":
                validation_events.append(payload["data"])

        event_bus.subscribe("plugin_custom_event", on_event)
        try:
            await plugin.handle_command("save_settings", {
                "server_url": "http://127.0.0.1:8000",  # default url should be overridden by qr payload
                "token": qr_json,
                "auth_mode": "token"
            })
        finally:
            event_bus.unsubscribe("plugin_custom_event", on_event)

        assert plugin.get_secret("SENTINEL_TOKEN") == "enc:v1:sample_aes_gcm_token"
        plugin.save_config.assert_called_with({"server_url": "https://192.168.1.97:8000"})
        assert plugin.is_authenticated is True
        assert plugin.auth_username == "black"
        assert len(validation_events) == 1
        assert validation_events[0]["success"] is True
        mock_verify.assert_called_with("enc:v1:sample_aes_gcm_token")
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
    assert dev["cover"] == "http://127.0.0.1:8000/api/covers/42?size=300"
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
