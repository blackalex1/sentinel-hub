import asyncio
import aiohttp
import time
import hmac
import hashlib
import base64
from pathlib import Path
from plugin_engine.base_plugin import BasePlugin
from core.event_bus import event_bus

import sys
import re

LRC_PATTERN = re.compile(r'\[(\d+):(\d+)(?:\.(\d+))?\](.*)')

class Plugin(BasePlugin):
    """
    Плагин текстов песен Яндекса (v2).
    Полностью асинхронный (aiohttp). Работает через EventBus.
    """
    def __init__(self, plugin_id: str):
        super().__init__(plugin_id)
        self._lyrics_cache = {}
        self._active_fetches = {}
        self._session = None

    async def on_start(self):
        # Добавляем User-Agent для стабильности запросов к внешним API
        headers = {
            "User-Agent": "MonitHome/2.0 (Coding Assistant; +https://github.com/blackalex1)"
        }
        self._session = aiohttp.ClientSession(headers=headers)
        
        # Подписываемся на события
        event_bus.subscribe("plugin_custom_event", self._on_event)
        event_bus.subscribe("ui_config_changed", self._on_config_changed)
        
        if self._is_tablet_control():
            self.log("MODE NOTICE: Tablet control is enabled. PC lyrics will be disabled.")
            await self.emit_state({"devices": {}})
        else:
            await self.emit_state({"devices": self._lyrics_cache})
        
        self.log("yandex_lyrics started.")

    async def on_stop(self):
        if self._session:
            await self._session.close()
        event_bus.unsubscribe("plugin_custom_event", self._on_event)
        event_bus.unsubscribe("ui_config_changed", self._on_config_changed)

    async def _on_config_changed(self, payload: dict):
        await self._check_and_apply_mode()

    async def _check_and_apply_mode(self):
        is_station_active = self._is_station_enabled()
        is_tablet = self._is_tablet_control()
        
        if not is_station_active or is_tablet:
            if self._lyrics_cache:
                reason = "Station disabled" if not is_station_active else "Tablet control active"
                self.log(f"Lyrics suspension: {reason}. Clearing cache.")
                self._lyrics_cache = {}
                await self.emit_state({"devices": {}})
        else:
            await self.emit_state({"devices": self._lyrics_cache})

    def _is_station_enabled(self):
        try:
            cfg_mgr = sys.modules.get('core.config')
            if cfg_mgr:
                active_plugins = getattr(cfg_mgr.config_manager.get(), "active_plugins", [])
                return "yandex_station" in active_plugins
        except: pass
        return True

    def _is_tablet_control(self):
        try:
            from core.config import config_manager
            station_cfg = config_manager.get_plugin_config("yandex_station")
            return station_cfg.get("tablet_control", False)
        except Exception as e:
            self.log(f"Error checking tablet control in DB: {e}", 10)
        return False

    async def _on_event(self, event_payload: dict):
        if not self._is_station_enabled() or self._is_tablet_control():
            return

        event_name = event_payload.get("event")
        if event_name == "track_changed":
            data = event_payload.get("data", {})
            await self._handle_track_change(
                data.get("device_id"), 
                data.get("track_id"),
                data.get("artist"),
                data.get("title")
            )
        elif event_name == "yandex_config":
            if self._is_tablet_control():
                self._lyrics_cache = {}
                await self.emit_state({"devices": {}})

    async def _handle_track_change(self, device_id: str, track_id: str, artist: str = None, title: str = None):
        if not device_id: return
        self.log(f"Track change detected for {device_id}: {track_id} ({artist} - {title})")
        
        if not track_id and not title:
            self._active_fetches[device_id] = None
            if device_id in self._lyrics_cache:
                del self._lyrics_cache[device_id]
                await self.emit_state({"devices": self._lyrics_cache})
            return

        current = self._lyrics_cache.get(device_id, {})
        track_key = track_id or f"search:{artist}:{title}"
        if current.get("track_id") == track_key:
            return

        self._active_fetches[device_id] = track_key
        loading_entry = {"track_id": track_key, "lyrics": "loading", "timings": []}
        self._lyrics_cache[device_id] = loading_entry
        await self.emit_state({"devices": self._lyrics_cache})
        await self.emit_event("lyrics", {"device_id": device_id, "data": loading_entry})
        
        async def delayed_fetch():
            await asyncio.sleep(0.3)
            if self._active_fetches.get(device_id) == track_key:
                await self._fetch_and_broadcast(device_id, track_id, artist, title)
                
        asyncio.create_task(delayed_fetch())

    async def _fetch_and_broadcast(self, device_id: str, track_id: str, artist: str, title: str):
        lyrics_data = await self._fetch_lyrics_parallel(track_id, artist, title)
        
        track_key = track_id or f"search:{artist}:{title}"
        if self._active_fetches.get(device_id) != track_key:
            return

        if lyrics_data:
            self.log(f"Lyrics: Found synced lyrics for {artist} - {title}", 20)
            lyrics_entry = {
                "track_id": track_key, 
                "lyrics": lyrics_data.get("full"),
                "timings": lyrics_data.get("timings")
            }
        else:
            self.log(f"Lyrics not available for {artist} - {title}", 30)
            lyrics_entry = {"track_id": track_key, "lyrics": "", "timings": []}
            
        self._lyrics_cache[device_id] = lyrics_entry
        await self.emit_state({"devices": self._lyrics_cache})
        await self.emit_event("lyrics", {"device_id": device_id, "data": lyrics_entry})

    def _sign_lyrics(self, track_id, timestamp):
        secret = b"p93jhgh689SBReK6ghtw62"
        msg = f"{track_id}{timestamp}".encode()
        hmac_hash = hmac.new(secret, msg, hashlib.sha256).digest()
        return base64.b64encode(hmac_hash).decode()

    def _parse_lrc(self, lrc_text):
        if not lrc_text: return []
        lines = []
        for line in lrc_text.splitlines():
            match = LRC_PATTERN.search(line)
            if match:
                m, s, ms, text = match.groups()
                ms = int(ms) if ms else 0
                if len(str(ms)) == 2: ms *= 10
                total_ms = (int(m) * 60 + int(s)) * 1000 + ms
                lines.append({"time": total_ms, "text": text.strip()})
        return lines

    async def _fetch_from_yandex_supplement(self, raw_track_id, headers):
        if not raw_track_id or not headers: return None
        try:
            async with self._session.get(f"https://api.music.yandex.net/tracks/{raw_track_id}/supplement", headers=headers, timeout=15) as r:
                if r.status == 200:
                    res = (await r.json()).get("result", {})
                    lyrics_obj = res.get("lyrics")
                    if lyrics_obj:
                        data = {"full": lyrics_obj.get("fullLyrics"), "timings": []}
                        major = lyrics_obj.get("major")
                        if major:
                            for line in major.get("lines", []):
                                data["timings"].append({"time": line.get("startTimeMs", 0), "text": line.get("words", "")})
                        return data
        except: pass
        return None

    async def _fetch_from_yandex_lrc(self, raw_track_id, headers):
        if not raw_track_id or not headers: return None
        try:
            ts = int(time.time())
            signature = self._sign_lyrics(raw_track_id, ts)
            url = f"https://api.music.yandex.net/tracks/{raw_track_id}/lyrics"
            async with self._session.get(url, headers=headers, params={"timeStamp": ts, "sign": signature}, timeout=15) as r:
                if r.status == 200:
                    download_url = (await r.json()).get("result", {}).get("downloadUrl")
                    if download_url:
                        async with self._session.get(download_url, timeout=15) as lrc_resp:
                            if lrc_resp.status == 200:
                                text = await lrc_resp.text()
                                return {"full": text, "is_lrc": True}
        except: pass
        return None

    async def _fetch_from_lrclib(self, artist, title):
        if not artist or not title: return None
        try:
            params = {"artist_name": artist, "track_name": title}
            async with self._session.get("https://lrclib.net/api/get", params=params, timeout=15) as r_lrc:
                if r_lrc.status == 200:
                    lrc_json = await r_lrc.json()
                    synced = lrc_json.get("syncedLyrics")
                    if synced:
                        return {"full": synced, "is_lrc": True}
                    return {"full": lrc_json.get("plainLyrics"), "is_lrc": False}
        except Exception as e:
            self.log(f"LRCLIB error ({type(e).__name__}): {str(e)}", 30)
        return None

    async def _fetch_lyrics_parallel(self, track_id, artist=None, title=None):
        x_token = self.get_secret("YANDEX_TOKEN")
        # Сохраняем headers в сессии или используем тут
        h = {"Authorization": f"OAuth {x_token}", "X-Yandex-Music-Client": "YandexMusicAndroid/24023621"} if x_token else {}

        # 1. По ID через Яндекс
        if track_id and h:
            raw_id = str(track_id).split(":")[0] if ":" in str(track_id) else str(track_id)
            # Yandex Supplement
            res = await self._fetch_from_yandex_supplement(raw_id, h)
            if res and res.get("timings"): return res
            # Yandex LRC
            res = await self._fetch_from_yandex_lrc(raw_id, h)
            if res and res.get("full"):
                res["timings"] = self._parse_lrc(res["full"])
                return res

        # 2. Фолбек на LRCLIB
        if artist and title:
            res = await self._fetch_from_lrclib(artist, title)
            if res:
                if res.get("is_lrc") and res.get("full"):
                    res["timings"] = self._parse_lrc(res["full"])
                elif res.get("full"):
                    res["timings"] = [{"time": 0, "text": res["full"]}]
                return res

        return None

    async def handle_command(self, action: str, data: any):
        pass
