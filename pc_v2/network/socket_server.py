import asyncio
import logging
import time
import msgpack
import socketio
from typing import Dict, Any

from core.config import config_manager
from core.event_bus import event_bus
from core.security import SecurityManager

# Импортируем хендлеры
from .handlers.ui import register_ui_handlers, get_ui_config_data
from .handlers.auth import register_auth_handlers
from .handlers.plugins import register_plugin_handlers

logger = logging.getLogger("SocketServer")
logger.setLevel(logging.INFO)

# Асинхронный сервер Socket.IO (разрешаем CORS для тестов)
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

class SocketServerManager:
    """Управляет подпиской на шину событий и рассылкой через Socket.IO"""
    def __init__(self):
        self.sio = sio
        # Кэш состояния для батчинга
        self._state_cache: Dict[str, Any] = {}
        self._dirty = False
        self._dirty_plugins = set()
        self.pairing_codes = {} # sid -> 4-digit code

    async def initialize(self):
        # Подписываемся на события от плагинов
        event_bus.subscribe("plugin_state_changed", self._on_plugin_state_changed)
        event_bus.subscribe("plugin_custom_event", self._on_plugin_custom_event)
        event_bus.subscribe("ui_config_changed", self._on_ui_config_changed)
        
        # Регистрация всех хендлеров событий
        register_auth_handlers(self.sio, self)
        register_ui_handlers(self.sio)
        register_plugin_handlers(self.sio)

        @self.sio.on("kick_device")
        async def handle_kick_device(sid, data):
            target_sid = data.get("sid")
            if target_sid:
                logger.info(f"Kicking device {target_sid} requested by {sid}")
                await self.sio.disconnect(target_sid)
                await self.update_devices()
        
        # Запускаем фоновую рассылку (батчинг)
        asyncio.create_task(self._broadcast_loop())

    async def update_devices(self):
        """Собирает список всех авторизованных устройств и рассылает его"""
        devices = []
        try:
            # Получаем все SID в комнате authorized
            authorized_sids = list(self.sio.manager.rooms.get('/', {}).get('authorized', []))
            for sid in authorized_sids:
                environ = self.sio.get_environ(sid)
                if not environ: continue
                
                # Используем улучшенную логику определения IP из auth.py
                from .handlers.auth import register_auth_handlers
                # Но лучше просто вынести get_real_ip в утилиты. 
                # Пока что скопируем или используем тот же подход.
                scope = environ.get('asgi.scope')
                if scope and 'client' in scope and scope['client']:
                    ip = scope['client'][0]
                else:
                    # Проверка X-Forwarded-For и прочих
                    xff = environ.get('HTTP_X_FORWARDED_FOR')
                    if xff:
                        ip = xff.split(',')[0].strip()
                    else:
                        ip = environ.get('HTTP_X_REAL_IP', environ.get('REMOTE_ADDR', 'Unknown'))
                
                ua = environ.get('HTTP_USER_AGENT', 'Unknown')
                device_type = "Browser"
                if "QtWebEngine" in ua: device_type = "PC GUI"
                elif "okhttp" in ua or "Android" in ua: device_type = "Tablet"
                
                devices.append({
                    "sid": sid,
                    "ip": ip,
                    "type": device_type,
                    "ua": ua
                })
            
            logger.debug(f"Broadcasting connected devices: {len(devices)}")
            await self.sio.emit('connected_devices', devices, room='authorized')
        except Exception as e:
            logger.error(f"Error updating devices list: {e}")

    async def _on_plugin_state_changed(self, payload: Dict[str, Any]):
        p_id = payload["plugin_id"]
        state = payload["state"]
        self._state_cache[p_id] = state
        self._dirty_plugins.add(p_id)
        self._dirty = True
        # Оповещаем UI, чтобы он мог перерисовать карточки (например, при получении прав)
        await self.sio.emit('plugin_state_changed', payload, room='authorized')

    async def _on_plugin_custom_event(self, payload: Dict[str, Any]):
        p_id = payload["plugin_id"]
        event_name = payload["event"]
        data = payload["data"]
        room = payload.get("room", "authorized")
        
        await self.sio.emit(f"plugin_event:{p_id}", {"event": event_name, "data": data}, room=room)
        
        # Для обратной совместимости
        if event_name == "yandex_config":
            await self.sio.emit("yandex_config", data, room=room)

    async def _on_ui_config_changed(self, payload: Dict[str, Any]):
        p_id = payload.get("plugin_id")
        logger.info(f"UI Config changed on server (plugin: {p_id}). Broadcasting to all clients.")
        
        # Обновляем конфиг у всех клиентов
        data = await get_ui_config_data()
        await self.sio.emit("ui_config", data, room='authorized')
        
        # Если изменились настройки Яндекса, принудительно обновляем конфиг на планшете
        if p_id == "yandex_station" or p_id is None:
            p = (await import_plugin_manager()).active_plugins.get("yandex_station")
            if p:
                await p.handle_command("get_yandex_config", {"sid": None})

    async def _broadcast_loop(self):
        """Рассылка MessagePack/JSON данных с частотой 10Hz (с батчингом дельт и 30с heartbeat)"""
        last_heartbeat = 0
        while True:
            await asyncio.sleep(0.1)
            
            now = time.time()
            is_heartbeat = (now - last_heartbeat > 30.0)
            if self._dirty or is_heartbeat:
                if not self._state_cache:
                    continue

                # Формируем дельту: отправляем только измененные с момента прошлой рассылки плагины.
                # Каждые 30 секунд (heartbeat) шлем полное состояние для синхронизации вновь подключенных клиентов.
                if is_heartbeat:
                    stats_to_send = self._state_cache
                else:
                    stats_to_send = {p_id: self._state_cache[p_id] for p_id in self._dirty_plugins if p_id in self._state_cache}
                    
                if not stats_to_send:
                    self._dirty = False
                    self._dirty_plugins.clear()
                    continue

                payload = {
                    "stats": stats_to_send,
                    "_server_time": now
                }
                
                try:
                    binary_payload = msgpack.packb(payload, use_bin_type=True)
                    key = config_manager.get_secret("ENCRYPTION_KEY")
                    if key:
                        final_payload = SecurityManager.encrypt_bytes(binary_payload, key)
                    else:
                        final_payload = binary_payload

                    await self.sio.emit('stats', final_payload, room='authorized')
                    await self.sio.emit('stats_json', payload, room='authorized')
                    
                    self._dirty = False
                    self._dirty_plugins.clear()
                    if is_heartbeat:
                        last_heartbeat = now
                except Exception as e:
                    logger.error(f"Broadcast error: {e}")

    async def _send_initial_data(self, sid):
        """Отправка текущего состояния сразу после подключения"""
        # Эмиттим события через хендлеры (вызываем их логику)
        data = await get_ui_config_data()
        await self.sio.emit("ui_config", data, room=sid)
        
        # Manager data
        plugins = []
        cfg = config_manager.get()
        import os
        from core.config import BUNDLE_DIR
        plugins_dir = os.path.join(BUNDLE_DIR, "plugins")
        if os.path.exists(plugins_dir):
            for d in os.listdir(plugins_dir):
                if os.path.isdir(os.path.join(plugins_dir, d)):
                    plugins.append({"id": d, "active": d in cfg.active_plugins})
        await self.sio.emit("manager_data", plugins, room=sid)
        
        # Yandex config
        pm = await import_plugin_manager()
        p = pm.active_plugins.get("yandex_station")
        if p:
            await p.handle_command("get_yandex_config", {"sid": sid})
        
        if self._state_cache:
            payload = {"stats": self._state_cache, "_server_time": time.time()}
            binary_payload = msgpack.packb(payload, use_bin_type=True)
            key = config_manager.get_secret("ENCRYPTION_KEY")
            if key:
                final_payload = SecurityManager.encrypt_bytes(binary_payload, key)
            else:
                final_payload = binary_payload

            await self.sio.emit('stats', final_payload, room=sid)
            await self.sio.emit('stats_json', payload, room=sid)

        # Отправляем список устройств
        await self.update_devices()

async def import_plugin_manager():
    from plugin_engine.manager import plugin_manager
    return plugin_manager

socket_manager = SocketServerManager()

# Обратная совместимость для старых импортов
async def handle_get_ui_config(sid):
    data = await get_ui_config_data()
    await sio.emit("ui_config", data, room=sid or 'authorized')

async def handle_get_manager_data(sid):
    # Упрощенная версия для обратной совместимости
    cfg = config_manager.get()
    plugins = [{"id": d, "active": d in cfg.active_plugins} for d in cfg.active_plugins]
    await sio.emit("manager_data", plugins, room=sid)

async def handle_get_yandex_config(sid):
    pm = await import_plugin_manager()
    p = pm.active_plugins.get("yandex_station")
    if p: await p.handle_command("get_yandex_config", {"sid": sid})
