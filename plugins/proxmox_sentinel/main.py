import asyncio
import logging
from typing import Any, Dict
from plugin_engine.base_plugin import BasePlugin

logger = logging.getLogger("Plugin.proxmox_sentinel")

class Plugin(BasePlugin):
    """
    Плагин интеграции Proxmox Sentinel (PVE Aegis) для экосистемы MonitHome / Sentinel Deck.
    Предоставляет централизованное управление конфигурацией и безопасным токеном,
    позволяя клиентам (планшетам Sentinel Deck) подключаться напрямую к серверу Proxmox по WSS.
    """
    def __init__(self, plugin_id: str):
        super().__init__(plugin_id)
        self.server_url = "https://192.168.1.89:8443"
        self.token = ""

    async def on_start(self):
        config = self.get_config()
        self.server_url = config.get("server_url", "https://192.168.1.89:8443").strip()
        self.token = self.get_secret("PROXMOX_SENTINEL_TOKEN", "").strip()

        self.log(f"Proxmox Sentinel plugin started. Target: {self.server_url}")
        await self._broadcast_status()

    async def on_stop(self):
        self.log("Proxmox Sentinel plugin stopped.")
        await self.emit_state({
            "active": False,
            "status": "stopped"
        })

    async def _broadcast_status(self):
        """Отправляет актуальные параметры подключения всем авторизованным клиентам (в т.ч. планшету)"""
        await self.emit_state({
            "active": True,
            "server_url": self.server_url,
            "token": self.token,
            "has_token": bool(self.token),
            "configured": bool(self.server_url and self.token),
            "status": "ready"
        })

    async def handle_command(self, action: str, data: Any):
        """Обработка команд от Web UI и планшета Sentinel Deck"""
        if action == "save_settings":
            if not isinstance(data, dict):
                return

            raw_url = str(data.get("server_url", "")).strip()
            raw_token = str(data.get("token", "")).strip()

            if raw_url:
                if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
                    raw_url = f"https://{raw_url}"
                self.server_url = raw_url.rstrip("/")
                self.save_config({"server_url": self.server_url})

            if raw_token:
                self.token = raw_token
                self.set_secret("PROXMOX_SENTINEL_TOKEN", self.token)

            self.log(f"Settings updated: URL={self.server_url}, Token={'set' if self.token else 'empty'}")
            await self._broadcast_status()

            await self.emit_event("settings_validation_result", {
                "success": True,
                "message": "Настройки Proxmox Sentinel успешно сохранены"
            })

        elif action == "get_settings":
            await self.emit_event("proxmox_settings_data", {
                "server_url": self.server_url,
                "token": self.token,
                "configured": bool(self.server_url and self.token)
            })

        elif action == "clear_alerts":
            self.log("Clear all alerts requested")
            await self.emit_event("proxmox_clear_alerts", {})
