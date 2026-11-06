import time
import json
import asyncio
from core.security import SecurityManager
from core.config import config_manager

class StateBroadcaster:
    def __init__(self, plugin):
        self.plugin = plugin

    async def push_state(self):
        config = self.plugin.get_config()
        selected_ids = self.plugin.get_secret("SELECTED_DEVICES", "").split(",")
        allowed_ids = [s.strip() for s in selected_ids if s.strip()]
        if not allowed_ids:
            allowed_ids = config.get("selected_device_ids", [])
        
        if config.get("tablet_control", False):
            minimal_devices = []
            for d_id, d in self.plugin.devices.items():
                if not allowed_ids or d_id in allowed_ids:
                    minimal_devices.append({"id": d_id, "name": d.get("name"), "status": "direct"})
            await self.plugin.emit_state({"devices": minimal_devices})
            return
            
        devices_list = []
        for d_id, s in self.plugin.states.items():
            if allowed_ids and d_id not in allowed_ids: continue
            dev_info = self.plugin.devices.get(d_id, {})
            devices_list.append({
                "id": d_id, 
                "name": dev_info.get("name", d_id), 
                "online": s.get("online", False),
                "playing": s.get("playing", False), "volume": s.get("volume", 0),
                "title": s.get("title", ""), "subtitle": s.get("artist", ""),
                "artist": s.get("artist", ""),
                "alice_state": s.get("alice_state", "IDLE"),
                "track_id": s.get("track_id", ""),
                "cover": s.get("cover", ""),
                "progress": s.get("progress", 0),
                "duration": s.get("duration", 0),
                "last_update": s.get("last_update", time.time())
            })
        await self.plugin.emit_state({"devices": devices_list})
        if devices_list:
            covers_found = sum(1 for d in devices_list if d.get("cover"))
            self.plugin.log(f"Pushed state for {len(devices_list)} devices. Covers found: {covers_found}", 10)

    async def broadcast_config_to_tablet(self, sid=None):
        config = self.plugin.get_config()
        y_token = self.plugin.get_secret("YANDEX_TOKEN")
        enc_key = config_manager.get_secret("ENCRYPTION_KEY")
        
        configs = []
        if config.get("tablet_control", False):
            selected_ids = self.plugin.get_secret("SELECTED_DEVICES", "").split(",")
            allowed_ids = [s.strip() for s in selected_ids if s.strip()]
            if not allowed_ids:
                allowed_ids = config.get("selected_device_ids", [])

            for d_id, d in self.plugin.devices.items():
                if allowed_ids and d_id not in allowed_ids: continue
                
                g_token = d.get("glagol_token")
                if g_token:
                    configs.append({
                        "id": d_id, 
                        "glagol_token": g_token, 
                        "name": d.get("name", "Яндекс Станция"), 
                        "ip": d.get("ip"),
                        "port": d.get("port", 1961)
                    })
        
        payload = {
            "devices": configs, 
            "yandex_token": y_token, 
            "enabled": config.get("tablet_control", False)
        }

        if enc_key:
            encrypted_data = SecurityManager.encrypt(json.dumps(payload), enc_key)
            final_event_data = {"encrypted": encrypted_data}
        else:
            final_event_data = payload

        await self.plugin.emit_event("yandex_config", final_event_data, room=sid)
        
        if sid:
            self.plugin.log(f"Broadcast: Config sent to client {sid}. Devices: {len(configs)}", 20)
        else:
            self.plugin.log(f"Broadcast: Config sent to all clients. Devices: {len(configs)}", 20)
