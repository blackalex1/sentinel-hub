import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from plugin_engine.base_plugin import BasePlugin
from core.event_bus import event_bus
from .client import SentinelClient

class Plugin(BasePlugin):
    """
    Плагин Sentinel Music для MonitHome (v2).
    Интегрирует персональную экосистему Sentinel:
    - Обнаружение и управление плеерами (Desktop, Android, Station, Web) через Sentinel Connect.
    - Передача метаданных, обложек альбомов, интерполированного прогресса трека.
    - Синхронизированные караоке-тексты песен из базы Sentinel / LRCLIB.
    """
    def __init__(self, plugin_id: str):
        super().__init__(plugin_id)
        self.client = SentinelClient()
        self.devices: Dict[str, Dict[str, Any]] = {}
        self.lyrics_cache: Dict[str, Dict[str, Any]] = {}
        self.last_track_ids: Dict[str, int] = {}
        
        self.is_authenticated = False
        self.auth_username: Optional[str] = None
        self._init_task: Optional[asyncio.Task] = None

        # Привязка событий клиента
        self.client.on_devices_update = self._on_devices_update
        self.client.on_device_state = self._on_device_state
        self.client.on_connection_change = self._on_connection_change

    async def on_start(self):
        config = self.get_config()
        server_url = config.get("server_url", "http://127.0.0.1:8000")
        token = self.get_secret("SENTINEL_TOKEN", "")
        
        self.client.set_config(server_url, token if token else None)
        self.log(f"Sentinel Music plugin starting. Server: {server_url}")

        # Первоначальная проверка аутентификации и запуск
        self._init_task = self.create_task(self._init_connection())

    async def on_stop(self):
        self.log("Stopping Sentinel Music plugin...")
        if self._init_task and not self._init_task.done():
            self._init_task.cancel()
            
        await self.client.close()
        self.devices.clear()
        self.lyrics_cache.clear()
        self.last_track_ids.clear()
        self.is_authenticated = False
        await self.emit_state({
            "online": False,
            "authenticated": False,
            "devices": []
        })

    async def _init_connection(self):
        """Проверяет токен и инициирует подключение к Sentinel Connect."""
        token = self.client.token
        if not token:
            self.log("No Sentinel token found. Waiting for authentication in settings.")
            self.is_authenticated = False
            self.auth_username = None
            await self._broadcast_current_state()
            return

        is_valid, username, err = await self.client.verify_token(token)
        if is_valid:
            self.is_authenticated = True
            self.auth_username = username
            self.log(f"Authenticated on Sentinel as '{username}'. Starting Sentinel Connect...")
            self.client.start_ws()
        else:
            self.log(f"Sentinel token verification failed: {err}", level=logging.WARNING)
            self.is_authenticated = False
            self.auth_username = None
            
        await self._broadcast_current_state()

    # --- Обработчики событий от SentinelClient ---

    async def _on_connection_change(self, connected: bool, reason: Optional[str]):
        self.log(f"Sentinel Connect WS state changed: connected={connected} ({reason or 'OK'})")
        await self._broadcast_current_state()

    async def _on_devices_update(self, devices_list: List[Dict[str, Any]]):
        """Обновление списка устройств."""
        new_devices = {}
        for d in devices_list:
            d_id = d.get("id")
            if not d_id:
                continue
            new_devices[d_id] = d
            
            # Проверяем трек для подгрузки текстов
            cur_track = d.get("current_track")
            if isinstance(cur_track, dict) and cur_track.get("id"):
                track_id = int(cur_track["id"])
                if self.last_track_ids.get(d_id) != track_id:
                    self.last_track_ids[d_id] = track_id
                    self.create_task(self._fetch_lyrics_for_device(d_id, track_id))

        self.devices = new_devices
        await self._broadcast_current_state()

    async def _on_device_state(self, device_id: str, device_data: Dict[str, Any]):
        """Обновление состояния конкретного плеера."""
        if device_id in self.devices:
            self.devices[device_id].update(device_data)
        else:
            self.devices[device_id] = device_data

        cur_track = device_data.get("current_track")
        if isinstance(cur_track, dict) and cur_track.get("id"):
            track_id = int(cur_track["id"])
            if self.last_track_ids.get(device_id) != track_id:
                self.last_track_ids[device_id] = track_id
                self.create_task(self._fetch_lyrics_for_device(device_id, track_id))

        await self._broadcast_current_state()

    async def _fetch_lyrics_for_device(self, device_id: str, track_id: int):
        """Асинхронная загрузка синхронизированного караоке-текста."""
        try:
            lines = await self.client.get_lyrics(track_id)
            lyrics_entry = {"timings": lines}
            self.lyrics_cache[device_id] = lyrics_entry
            
            # Эмитим событие караоке для UI
            await self.emit_event("lyrics", {"device_id": device_id, "data": lyrics_entry})
            await self._broadcast_current_state()
        except Exception as e:
            self.log(f"Error fetching lyrics for device {device_id}, track {track_id}: {e}", level=logging.DEBUG)

    # --- Формирование состояния для MediaWidget ---

    async def _broadcast_current_state(self):
        """Формирует и отправляет агрегированное состояние в шину EventBus."""
        now = time.time()
        formatted_devices = []
        
        # Активное устройство (приоритет: то, которое сейчас играет)
        active_device: Optional[Dict[str, Any]] = None

        for d_id, raw_dev in self.devices.items():
            track = raw_dev.get("current_track") or {}
            track_id = track.get("id")
            
            cover_url = ""
            if track_id:
                cover_url = f"{self.client.server_url}/covers/{track_id}?size=300"
            elif track.get("cover_url"):
                cover_url = track.get("cover_url")
                if cover_url.startswith("/"):
                    cover_url = f"{self.client.server_url}{cover_url}"

            is_playing = bool(raw_dev.get("is_playing", False))
            pos_sec = float(raw_dev.get("position_ms", 0)) / 1000.0
            dur_sec = float(raw_dev.get("duration_ms", 0)) / 1000.0
            vol_int = int(float(raw_dev.get("volume", 1.0)) * 100)
            lyrics = self.lyrics_cache.get(d_id, {}).get("timings", [])

            dev_state = {
                "id": d_id,
                "name": raw_dev.get("name", "Sentinel Player"),
                "title": track.get("title", ""),
                "artist": track.get("artist", ""),
                "cover": cover_url,
                "playing": is_playing,
                "progress": pos_sec,
                "duration": dur_sec,
                "volume": vol_int,
                "online": True,
                "status": "playing" if is_playing else "idle",
                "local_last_update": now,
                "timings": lyrics
            }
            formatted_devices.append(dev_state)

            if is_playing and active_device is None:
                active_device = dev_state

        if active_device is None and formatted_devices:
            active_device = formatted_devices[0]

        top_title = active_device["title"] if active_device else ""
        top_artist = active_device["artist"] if active_device else ""
        top_cover = active_device["cover"] if active_device else ""
        top_playing = active_device["playing"] if active_device else False
        top_progress = active_device["progress"] if active_device else 0.0
        top_duration = active_device["duration"] if active_device else 0.0
        top_volume = active_device["volume"] if active_device else 100

        state = {
            "online": self.client._is_connected,
            "authenticated": self.is_authenticated,
            "auth_required": not self.is_authenticated,
            "server_url": self.client.server_url,
            "devices": formatted_devices,
            "devices_lyrics": self.lyrics_cache,
            # Поля верхнего уровня для совместимости с одиночными источниками
            "title": top_title,
            "artist": top_artist,
            "cover": top_cover,
            "playing": top_playing,
            "progress": top_progress,
            "duration": top_duration,
            "volume": top_volume,
            "local_last_update": now
        }

        await self.emit_state(state)

    # --- Управление командами (UI -> Plugin) ---

    async def handle_command(self, action: str, data: Any):
        self.log(f"Handling command: action={action}, data={data}")
        
        # 1. Получение данных для модального окна настроек
        if action == "get_settings_data":
            token = self.get_secret("SENTINEL_TOKEN", "")
            response = {
                "server_url": self.client.server_url,
                "has_token": bool(token),
                "username": self.auth_username,
                "is_authenticated": self.is_authenticated,
                "is_connected": self.client._is_connected,
                "devices": [
                    {"id": d_id, "name": d.get("name", d_id), "playing": d.get("is_playing", False)}
                    for d_id, d in self.devices.items()
                ]
            }
            await self.emit_event("settings_data", response)

        # 2. Сохранение настроек / Авторизация
        elif action == "save_settings":
            await self._handle_save_settings(data if isinstance(data, dict) else {})

        # 3. Выход из аккаунта
        elif action == "logout":
            self.set_secret("SENTINEL_TOKEN", "")
            self.client.set_config(self.client.server_url, None)
            await self.client.disconnect_ws()
            self.is_authenticated = False
            self.auth_username = None
            self.devices.clear()
            self.lyrics_cache.clear()
            await self._broadcast_current_state()
            await self.emit_event("settings_validation_result", {"success": True, "message": "Успешный выход"})

        # 4. Команды воспроизведения от MediaWidget
        else:
            await self._handle_playback_command(action, data)

    async def _handle_save_settings(self, payload: Dict[str, Any]):
        server_url = payload.get("server_url", "").strip().rstrip("/")
        if not server_url:
            server_url = "http://127.0.0.1:8000"

        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        token_input = (payload.get("token") or "").strip()

        # Сохраняем URL сервера
        self.save_config({"server_url": server_url})
        self.client.server_url = server_url

        target_token = None

        # Сценарий А: Вход по логину и паролю
        if username and password and password != "******":
            self.log(f"Attempting login to {server_url} as {username}...")
            ok, tok, user, err = await self.client.login(username, password)
            if not ok:
                await self.emit_event("settings_validation_result", {
                    "success": False,
                    "message": f"Ошибка авторизации: {err}"
                })
                return
            target_token = tok
            self.auth_username = user
            self.is_authenticated = True

        # Сценарий Б: Ввод токена напрямую
        elif token_input and token_input != "******":
            self.log(f"Validating provided token on {server_url}...")
            ok, user, err = await self.client.verify_token(token_input)
            if not ok:
                await self.emit_event("settings_validation_result", {
                    "success": False,
                    "message": f"Неверный токен: {err}"
                })
                return
            target_token = token_input
            self.auth_username = user
            self.is_authenticated = True

        # Сценарий В: Изменение только URL (используем уже сохраненный токен)
        else:
            existing_token = self.get_secret("SENTINEL_TOKEN", "")
            if existing_token:
                ok, user, err = await self.client.verify_token(existing_token)
                if ok:
                    target_token = existing_token
                    self.auth_username = user
                    self.is_authenticated = True
                else:
                    await self.emit_event("settings_validation_result", {
                        "success": False,
                        "message": f"Сессия истекла: {err}"
                    })
                    return

        if target_token:
            self.set_secret("SENTINEL_TOKEN", target_token)
            self.client.set_config(server_url, target_token)
            
            # Переподключаем WebSocket
            await self.client.disconnect_ws()
            self.client.start_ws()

        await self._broadcast_current_state()
        await self.emit_event("settings_validation_result", {
            "success": True,
            "message": f"Подключено к Sentinel ({self.auth_username})"
        })

    async def _handle_playback_command(self, action: str, data: Any):
        """Маршрутизация команд управления медиа."""
        # Определение целевого устройства
        target_device_id = None
        if isinstance(data, str) and data.strip():
            target_device_id = data.strip()
        elif isinstance(data, dict):
            target_device_id = data.get("device_id") or data.get("target")

        # Если устройство не указано, берем играющее или первое доступное
        if not target_device_id:
            for d_id, d in self.devices.items():
                if d.get("is_playing"):
                    target_device_id = d_id
                    break
            if not target_device_id and self.devices:
                target_device_id = next(iter(self.devices.keys()))

        if not target_device_id:
            self.log("No active Sentinel player found to send command to.", level=logging.WARNING)
            return

        if action == "play_pause":
            await self.client.send_command(target_device_id, "TOGGLE_PLAY")

        elif action == "next_track":
            await self.client.send_command(target_device_id, "NEXT")

        elif action == "prev_track":
            await self.client.send_command(target_device_id, "PREV")

        elif action.startswith("seek:"):
            try:
                seconds = float(action.split(":", 1)[1])
                pos_ms = int(seconds * 1000)
                await self.client.send_command(target_device_id, "SEEK", {"position_ms": pos_ms})
            except Exception as e:
                self.log(f"Invalid seek command {action}: {e}")

        elif action.startswith("set_volume:"):
            try:
                vol_int = int(action.split(":", 1)[1])
                vol_float = max(0.0, min(1.0, float(vol_int) / 100.0))
                await self.client.send_command(target_device_id, "SET_VOLUME", {"volume": vol_float})
            except Exception as e:
                self.log(f"Invalid volume command {action}: {e}")
