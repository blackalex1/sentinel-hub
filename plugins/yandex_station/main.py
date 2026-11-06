import asyncio
import json
import time
import os
from plugin_engine.base_plugin import BasePlugin
from .auth import YandexAuth
from .worker import monitor_request_state
from core.event_bus import event_bus
from core.network.zeroconf_service import ZeroconfService
from zeroconf import ServiceBrowser
from .discovery import SpeakerDiscovery
from .device_manager import DeviceManager
from .broadcaster import StateBroadcaster

class Plugin(BasePlugin):
    """
    Плагин Я.Станции v2 (полностью асинхронный).
    Управляет колонками локально через Glagol API.
    """
    def __init__(self, plugin_id: str):
        super().__init__(plugin_id)
        self.devices = {}
        self.states = {}
        self.cmd_queues = {} 
        self.workers = {}
        self.connections = {} 
        self.control_conns = {} 
        self._force_broadcast_until = {}
        
        # Модули
        self.auth = YandexAuth(self)
        self.discovery = SpeakerDiscovery()
        self.device_manager = DeviceManager(self)
        self.broadcaster = StateBroadcaster(self)
        
        self.zeroconf = None

    async def on_start(self):
        self.loop = asyncio.get_running_loop()
        
        # Сначала загружаем кэшированные токены из БД
        self._load_tokens()
        
        if not self.auth.has_token():
            self.log("Yandex token missing. Waiting for manual login...", 20)
        else:
            self.log("Yandex tokens loaded from cache.", 20)

        # Запускаем mDNS поиск
        from .discovery import get_all_interfaces
        interfaces = get_all_interfaces()
        self.log(f"Initializing unified Zeroconf on interfaces: {interfaces}")
        try:
            zc_service = await ZeroconfService.get_instance()
            # Пытаемся инициализировать с интерфейсами плагина, если еще не инициализировано
            self.aio_zeroconf = await zc_service.initialize(interfaces=interfaces)
            self.browser = ServiceBrowser(self.aio_zeroconf.zeroconf, "_yandexio._tcp.local.", self)
        except Exception as e:
            self.log(f"Failed to use unified Zeroconf: {e}", 40)
        
        event_bus.subscribe("ui_config_changed", self._on_config_changed)
        
        # Запускаем поиск и применяем режим (запуск воркеров)
        await self.device_manager.apply_mode()
    
    async def _on_config_changed(self, payload: dict):
        if payload.get("plugin_id") == self.plugin_id or payload.get("plugin_id") is None:
            sid = payload.get("sid")
            await self.device_manager.apply_mode(sid)

    async def on_stop(self):
        self.log("Stopping Yandex Station plugin...")
        if hasattr(self, 'browser') and self.browser:
            self.browser.cancel()
        for d_id, worker in self.workers.items():
            worker.stop()

    def _load_tokens(self):
        raw_glagol = self.get_secret("GLAGOL_TOKENS")
        if not raw_glagol:
            if self.auth.has_token():
                asyncio.create_task(self.auth.refresh_tokens_sync())
            return

        try:
            self.devices = json.loads(raw_glagol)
            cached_ips = self.get_config().get("cached_ips", {})
            for d_id, d in self.devices.items():
                if d_id in cached_ips: d["ip"] = cached_ips[d_id]
                self.states[d_id] = {
                    "name": d.get("name", "Колонка"), "platform": d.get("platform"),
                    "online": False, "volume": 0, "playing": False,
                    "title": "", "artist": "", "cover": "",
                    "track_id": "", "alice_state": "IDLE"
                }
        except Exception as e:
            self.log(f"Error parsing glagol tokens: {e}", 40)

    # mDNS Handlers (Interface for Zeroconf)
    def add_service(self, zc, type, name):
        info = zc.get_service_info(type, name)
        if info:
            import ipaddress
            addresses = [str(ipaddress.ip_address(addr)) for addr in info.addresses if len(addr) == 4]
            props = {k.decode(): v.decode() if isinstance(v, bytes) else v for k, v in info.properties.items()}
            d_id = props.get("deviceId")
            if d_id and addresses:
                ip = addresses[0]
                if d_id in self.devices:
                    old_ip = self.devices[d_id].get("ip")
                    if old_ip != ip:
                        self.log(f"Device {d_id} IP updated: {old_ip} -> {ip}")
                        self.devices[d_id]["ip"] = ip
                        cached_ips = self.get_config().get("cached_ips", {})
                        cached_ips[d_id] = ip
                        self.save_config({"cached_ips": cached_ips})
                        # Вещаем конфиг только при РЕАЛЬНОМ изменении IP
                        asyncio.run_coroutine_threadsafe(self.broadcaster.broadcast_config_to_tablet(), self.loop)

    def update_service(self, zc, type, name):
        self.add_service(zc, type, name)

    def remove_service(self, zc, type, name):
        pass

    async def handle_command(self, action: str, data: any):
        if action == "get_yandex_config":
            sid = data.get("sid") if isinstance(data, dict) else None
            await self.broadcaster.broadcast_config_to_tablet(sid)
        elif action == "get_wizard_data":
            config = self.get_config()
            devices_list = [{"id": d_id, "name": d.get("name", d_id)} for d_id, d in self.devices.items()]
            selected_ids = self.get_secret("SELECTED_DEVICES", "").split(",")
            selected_ids = [s.strip() for s in selected_ids if s.strip()] or config.get("selected_device_ids", [])
            await self.emit_event("wizard_data", {
                "devices": devices_list, "tablet_control": config.get("tablet_control", False), "selected_device_ids": selected_ids
            })
        elif action == "handle_wizard":
            self.save_config({"tablet_control": data.get("tablet_control", False)})
            self.set_secret("SELECTED_DEVICES", ",".join(data.get("selected_device_ids", [])))
            await self.device_manager.apply_mode()
        elif action == "start_qr_login":
            asyncio.create_task(self.auth.start_qr_login())
        elif action == "get_qr_status":
            asyncio.create_task(self.auth._emit_qr_status())
        else:
            await self.device_manager.handle_device_command(action, data)
