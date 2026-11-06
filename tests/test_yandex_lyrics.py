import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from plugins.yandex_lyrics.main import Plugin, LRC_PATTERN

def test_yandex_lyrics_parse_lrc():
    plugin = Plugin("yandex_lyrics")
    
    lrc_data = """[00:12.34] Verse 1 line
[01:05] Chorus line
[02:10.50] Another line
"""
    parsed = plugin._parse_lrc(lrc_data)
    
    assert len(parsed) == 3
    # 00:12.34 -> 12 * 1000 + 340 = 12340 ms
    assert parsed[0] == {"time": 12340, "text": "Verse 1 line"}
    # 01:05 -> 65 * 1000 = 65000 ms
    assert parsed[1] == {"time": 65000, "text": "Chorus line"}
    # 02:10.5 -> (2 * 60 + 10) * 1000 + 500 = 130500 ms
    assert parsed[2] == {"time": 130500, "text": "Another line"}

def test_yandex_lyrics_signature():
    plugin = Plugin("yandex_lyrics")
    sig = plugin._sign_lyrics("123456", 1718274820)
    assert isinstance(sig, str)
    assert len(sig) > 10

@pytest.mark.asyncio
async def test_yandex_lyrics_fetch_lrclib():
    plugin = Plugin("yandex_lyrics")
    
    # Mock aiohttp ClientSession
    mock_session = MagicMock()
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json.return_value = {
        "syncedLyrics": "[00:10.00] Synced Lyrics Line\n",
        "plainLyrics": "Plain Lyrics Line"
    }
    
    # Mock async context manager for session.get
    mock_session.get.return_value.__aenter__.return_value = mock_resp
    plugin._session = mock_session
    
    result = await plugin._fetch_from_lrclib("Some Artist", "Some Title")
    assert result is not None
    assert result["full"] == "[00:10.00] Synced Lyrics Line\n"
    assert result["is_lrc"] is True
