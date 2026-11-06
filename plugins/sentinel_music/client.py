import asyncio
import logging
import json
import time
import urllib.parse
import re
from typing import Optional, Dict, Any, List, Callable, Tuple
import aiohttp

logger = logging.getLogger("Plugin.sentinel_music.client")


def parse_token_input(raw_input: Optional[str]) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Интеллектуальный парсер токена авторизации Sentinel Music.
    Поддерживает:
    1. JSON строку сопряжения из UI QR-кода: {"url":"...", "token":"enc:v1:...", "username":"..."}
    2. Зашифрованный токен AES-256-GCM: enc:v1:...
    3. Токен с префиксом 'Bearer ' или 'bearer '
    4. Токен в одинарных или двойных кавычках
    5. URL-encoded токен (enc%3Av1%3A...)
    6. Стандартный токен сессии (secrets.token_urlsafe)
    Возвращает: (clean_token, extracted_url, extracted_username)
    """
    if not raw_input:
        return "", None, None

    text = str(raw_input).strip().strip('"\'')
    extracted_url: Optional[str] = None
    extracted_user: Optional[str] = None

    # 1. Проверяем, является ли ввод JSON объектом сопряжения (из QR модала Web UI)
    if text.startswith("{") and ("token" in text or "t" in text):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                raw_tok = data.get("token") or data.get("t") or ""
                extracted_url = data.get("url") or data.get("server") or data.get("server_url")
                extracted_user = data.get("username") or data.get("u")
                text = str(raw_tok).strip().strip('"\'')
        except Exception:
            pass

    # 2. Декодируем URL-encoded строку (например enc%3Av1%3A...)
    if "%" in text:
        try:
            text = urllib.parse.unquote(text)
        except Exception:
            pass

    # 3. Срезаем префикс Bearer (регистронезависимо)
    if text.lower().startswith("bearer "):
        text = text[7:].strip()

    # 4. Финальная очистка пробелов и кавычек
    text = text.strip().strip('"\'')

    return text, extracted_url, extracted_user


def normalize_server_url(url: Optional[str]) -> str:
    """
    Нормализует базовый URL сервера Sentinel Music:
    - Добавляет http:// если схема не указана
    - Удаляет завершающие слэши
    - Удаляет завершающий префикс /api, чтобы эндпоинты формировались предсказуемо
    """
    u = (url or "").strip().rstrip("/")
    if not u:
        return "http://127.0.0.1:8000"
    if not (u.startswith("http://") or u.startswith("https://")):
        u = "http://" + u
    u = u.rstrip("/")
    if u.endswith("/api"):
        u = u[:-4].rstrip("/")
    return u


class SentinelClient:
    """
    Клиент для взаимодействия с Sentinel Music Server:
    1. REST API: аутентификация (/api/auth/login, /api/auth/me), тексты песен (/api/lyrics/{id}).
    2. WebSocket: протокол Sentinel Connect (/api/remote/ws) для управления в реальном времени.
    """
    def __init__(self, server_url: str = "http://127.0.0.1:8000"):
        self.server_url = normalize_server_url(server_url)
        self.token: Optional[str] = None
        self.device_id = "monithome_pc_hub"
        self.device_name = "MonitHome PC Hub"
        
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._is_connected = False
        
        # Callbacks
        self.on_devices_update: Optional[Callable[[List[Dict[str, Any]]], Any]] = None
        self.on_device_state: Optional[Callable[[str, Dict[str, Any]], Any]] = None
        self.on_connection_change: Optional[Callable[[bool, Optional[str]], Any]] = None

    def set_config(self, server_url: str, token: Optional[str] = None):
        self.server_url = normalize_server_url(server_url)
        clean_tok, _, _ = parse_token_input(token)
        self.token = clean_tok if clean_tok else None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {
                "User-Agent": "MonitHome/2.0 (Sentinel Plugin; Windows)"
            }
            # Разрешаем подключение по HTTPS к локальным серверам с самоподписанными SSL-сертификатами
            connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(headers=headers, connector=connector)
        return self._session

    async def close(self):
        """Останавливает WebSocket и закрывает HTTP-сессию."""
        self._is_running = False
        await self.disconnect_ws()
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # --- REST API ---

    async def login(self, username: str, password: str, device_name: str = "MonitHome Hub") -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Авторизация по логину и паролю.
        Поддерживает маршруты /api/auth/login с фолбэком на /auth/login.
        Возвращает: (success, token, username, error_message)
        """
        session = await self._get_session()
        endpoints = [f"{self.server_url}/api/auth/login", f"{self.server_url}/auth/login"]
        payload = {
            "username": username.strip(),
            "password": password,
            "device_name": device_name
        }
        last_err = None
        for url in endpoints:
            try:
                async with session.post(url, json=payload, ssl=False, timeout=aiohttp.ClientTimeout(total=8.0)) as resp:
                    if resp.status == 404:
                        continue
                    data = await resp.json()
                    if resp.status == 200 and data.get("status") == "ok":
                        token = data.get("token")
                        user = data.get("username", username)
                        return True, token, user, None
                    detail = data.get("detail", "Ошибка авторизации")
                    return False, None, None, str(detail)
            except Exception as e:
                logger.warning(f"Login failed on {url}: {e}")
                last_err = str(e)
                break

        return False, None, None, f"Ошибка соединения: {last_err or 'Не удалось подключиться к серверу'}"

    async def verify_token(self, token: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Проверка валидности сессионного токена.
        Поддерживает чистые токены, зашифрованные токены AES-256-GCM (enc:v1:...) и QR JSON-строки.
        Проверяет маршруты /api/auth/me (с фолбэком на /auth/me).
        Возвращает: (is_valid, username, error_message)
        """
        clean_token, _, _ = parse_token_input(token or self.token or "")
        if not clean_token:
            return False, None, "Токен не указан"
            
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {clean_token}"}
        endpoints = [f"{self.server_url}/api/auth/me", f"{self.server_url}/auth/me"]
        last_err = None

        for url in endpoints:
            try:
                async with session.get(url, headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=6.0)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return True, data.get("username"), None
                    elif resp.status in (401, 403):
                        return False, None, "Токен недействителен или истек (401 Unauthorized)"
                    elif resp.status == 404:
                        last_err = f"Маршрут не найден (404 на {url})"
                        continue
                    else:
                        return False, None, f"Сервер вернул статус {resp.status}"
            except Exception as e:
                last_err = str(e)
                break

        return False, None, f"Не удалось подключиться: {last_err or 'Ошибка проверки токена'}"

    async def get_lyrics(self, track_id: int) -> List[Dict[str, Any]]:
        """
        Получение синхронизированных караоке-таймингов текста песни:
        Возвращает: [{"time": ms, "text": "..."}]
        """
        if not track_id:
            return []
            
        session = await self._get_session()
        endpoints = [f"{self.server_url}/api/lyrics/{track_id}", f"{self.server_url}/lyrics/{track_id}"]
        headers = {}
        if self.token:
            clean_tok, _, _ = parse_token_input(self.token)
            headers["Authorization"] = f"Bearer {clean_tok}"
            
        for url in endpoints:
            try:
                async with session.get(url, headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        lines = data.get("lines")
                        if isinstance(lines, list):
                            return lines
                    elif resp.status == 404:
                        continue
            except Exception as e:
                logger.debug(f"Failed to fetch lyrics from {url}: {e}")
                break
            
        return []

    # --- Sentinel Connect (WebSocket) ---

    def start_ws(self):
        """Запускает фоновый процесс поддержания WebSocket соединения."""
        if self._is_running:
            return
        self._is_running = True
        self._ws_task = asyncio.create_task(self._ws_loop())

    async def disconnect_ws(self):
        """Отключает текущий сокет."""
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
            self._ping_task = None
            
        if self._ws and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
            
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            self._ws_task = None
            
        self._set_connected(False, "Disconnected")

    def _set_connected(self, connected: bool, reason: Optional[str] = None):
        if self._is_connected != connected:
            self._is_connected = connected
            if self.on_connection_change:
                try:
                    res = self.on_connection_change(connected, reason)
                    if asyncio.iscoroutine(res):
                        asyncio.create_task(res)
                except Exception as e:
                    logger.error(f"Error in on_connection_change callback: {e}")

    async def _ws_loop(self):
        """Постоянный цикл подключения с автореконнектом."""
        retry_delay = 2.0
        while self._is_running:
            if not self.token:
                self._set_connected(False, "No token configured")
                await asyncio.sleep(3.0)
                continue

            clean_tok, _, _ = parse_token_input(self.token)
            session = await self._get_session()
            
            parsed = urllib.parse.urlparse(self.server_url)
            ws_scheme = "wss" if parsed.scheme == "https" else "ws"
            netloc = parsed.netloc
            query = urllib.parse.urlencode({
                "token": clean_tok,
                "device_id": self.device_id,
                "device_name": self.device_name,
                "device_type": "remote"
            })
            
            ws_urls = [
                f"{ws_scheme}://{netloc}/api/remote/ws?{query}",
                f"{ws_scheme}://{netloc}/remote/ws?{query}"
            ]

            connected_ok = False
            for ws_url in ws_urls:
                if not self._is_running:
                    break
                ws_clean_display = ws_url.split("?")[0]
                logger.info(f"Connecting to Sentinel Connect WS: {ws_clean_display}...")
                try:
                    async with session.ws_connect(ws_url, ssl=False, timeout=10.0, heartbeat=30.0) as ws:
                        self._ws = ws
                        self._set_connected(True)
                        retry_delay = 2.0
                        connected_ok = True
                        logger.info(f"Successfully connected to Sentinel Connect WS via {ws_clean_display}.")
                        
                        # Запускаем пинг таск
                        self._ping_task = asyncio.create_task(self._ping_loop())
                        
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    payload = json.loads(msg.data)
                                    await self._handle_ws_message(payload)
                                except Exception as e:
                                    logger.error(f"Error parsing WS message: {e}")
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
                        break
                except aiohttp.WSServerHandshakeError as e:
                    if e.status == 404:
                        continue
                    logger.warning(f"Sentinel Connect WS handshake failed on {ws_clean_display}: {e}")
                    self._set_connected(False, str(e))
                    break
                except asyncio.CancelledError:
                    return
                except Exception as e:
                    logger.warning(f"Sentinel Connect WS connection failed on {ws_clean_display}: {e}")
                    self._set_connected(False, str(e))
                    break
                finally:
                    if self._ping_task and not self._ping_task.done():
                        self._ping_task.cancel()
                        self._ping_task = None
                    self._ws = None
                    self._set_connected(False)

            if not connected_ok and self._is_running:
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 20.0)

    async def _ping_loop(self):
        """Периодический пинг сервера для удержания канала."""
        try:
            while self._is_connected and self._ws and not self._ws.closed:
                await asyncio.sleep(25.0)
                if self._ws and not self._ws.closed:
                    await self._ws.send_json({"action": "ping"})
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Ping error: {e}")

    async def _handle_ws_message(self, data: Dict[str, Any]):
        msg_type = data.get("type")
        if msg_type in ("welcome", "devices_update"):
            devices = data.get("devices", [])
            if self.on_devices_update:
                res = self.on_devices_update(devices)
                if asyncio.iscoroutine(res):
                    await res
        elif msg_type == "device_state":
            device_id = data.get("device_id")
            device_data = data.get("device", {})
            if device_id and self.on_device_state:
                res = self.on_device_state(device_id, device_data)
                if asyncio.iscoroutine(res):
                    await res

    async def send_command(self, target_device_id: str, command: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        """
        Отправка команды удаленному плееру (Sentinel Connect):
        command: TOGGLE_PLAY, PLAY, PAUSE, NEXT, PREV, SEEK, SET_VOLUME, etc.
        """
        cmd_upper = command.upper()
        # 1. Попытка отправки через активный сокет
        if self._ws and not self._ws.closed and self._is_connected:
            msg = {
                "action": "command",
                "target_device_id": target_device_id,
                "command": cmd_upper,
                "payload": payload or {}
            }
            try:
                await self._ws.send_json(msg)
                return True
            except Exception as e:
                logger.warning(f"Failed to send WS command: {e}. Trying REST fallback...")

        # 2. REST Fallback
        if not self.token:
            return False
            
        clean_tok, _, _ = parse_token_input(self.token)
        session = await self._get_session()
        endpoints = [
            f"{self.server_url}/api/remote/command",
            f"{self.server_url}/remote/command"
        ]
        headers = {"Authorization": f"Bearer {clean_tok}"}
        req_body = {
            "target_device_id": target_device_id,
            "command": cmd_upper,
            "payload": payload or {}
        }
        for url in endpoints:
            try:
                async with session.post(url, json=req_body, headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
                    if resp.status == 200:
                        return True
                    if resp.status == 404:
                        continue
                    return False
            except Exception as e:
                logger.error(f"Failed to send REST command to {url}: {e}")
                break
        return False
