import asyncio
import time
import uuid
from .worker import DeviceWorker, monitor_request_state

class DeviceManager:
    def __init__(self, plugin):
        self.plugin = plugin

    async def apply_mode(self, sid: str = None):
        """Применяет текущий режим управления (Локально / Планшет)"""
        config = self.plugin.get_config()
        is_tablet = config.get("tablet_control", False)
        
        mode_str = "STANDALONE (Tablet)" if is_tablet else "PC CONTROL"
        self.plugin.log(f"Mode applied: {mode_str}", 20)

        selected_ids = self.plugin.get_secret("SELECTED_DEVICES", "").split(",")
        selected_ids = [s.strip() for s in selected_ids if s.strip()]
        if not selected_ids:
            selected_ids = config.get("selected_device_ids", [])

        # УПРАВЛЕНИЕ ВОРКЕРАМИ
        if is_tablet:
            for d_id in list(self.plugin.workers.keys()):
                self.plugin.log(f"Stopping worker (Standalone mode active): {d_id}")
                self.plugin.workers[d_id].stop()
                del self.plugin.workers[d_id]
                if d_id in self.plugin.cmd_queues: del self.plugin.cmd_queues[d_id]
            
            # Очищаем метаданные, чтобы не висел старый текст/обложка
            for d_id in self.plugin.states:
                self.plugin.states[d_id].update({
                    "playing": False,
                    "title": "",
                    "artist": "",
                    "cover": "",
                    "track_id": "",
                    "alice_state": "IDLE"
                })
        else:
            for d_id in list(self.plugin.workers.keys()):
                if selected_ids and d_id not in selected_ids:
                    self.plugin.log(f"Stopping worker for unselected device: {d_id}")
                    if d_id in self.plugin.workers:
                        self.plugin.workers[d_id].stop()
                        del self.plugin.workers[d_id]
                    if d_id in self.plugin.cmd_queues: del self.plugin.cmd_queues[d_id]

            for d_id in selected_ids:
                if d_id in self.plugin.devices and d_id not in self.plugin.workers:
                    self.plugin.log(f"Starting worker for: {d_id}")
                    self.plugin.cmd_queues[d_id] = asyncio.Queue()
                    self.plugin._force_broadcast_until[d_id] = 0
                    worker = DeviceWorker(self.plugin, d_id)
                    self.plugin.workers[d_id] = worker
                    worker.start()

        # Рассылка конфига
        if sid:
            async def delayed_broadcast():
                await asyncio.sleep(0.5)
                await self.plugin.broadcaster.broadcast_config_to_tablet(sid)
            asyncio.create_task(delayed_broadcast())
        else:
            await self.plugin.broadcaster.broadcast_config_to_tablet()

        if not is_tablet:
            for d_id, state in self.plugin.states.items():
                track_id = state.get("track_id")
                if track_id:
                    await self.plugin.emit_event("track_changed", {"device_id": d_id, "track_id": track_id})
        
        await self.plugin.broadcaster.push_state()

    async def handle_device_command(self, action: str, data: any):
        if not isinstance(data, dict): data = {}
        target = data.get("device_id")
        if not target or target not in self.plugin.cmd_queues: return

        cmd = action.split(":", 1)[0]
        val = action.split(":", 1)[1] if ":" in action else None
        payload_data = None
        
        if cmd == "play_pause":
            is_playing = self.plugin.states.get(target, {}).get("playing", False)
            self.plugin.states[target]["playing"] = not is_playing
            payload_data = {"command": "stop" if is_playing else "play"}
            self.plugin._force_broadcast_until[target] = time.time() + 3.0
        elif cmd == "next_track":
            payload_data = {"command": "next"}
            self.plugin.states[target].update({"title": self.plugin.i18n("loading", "Загрузка..."), "playing": True})
            self.plugin._force_broadcast_until[target] = time.time() + 5.0
        elif cmd == "prev_track":
            payload_data = {"command": "prev"}
            self.plugin.states[target].update({"title": self.plugin.i18n("loading", "Загрузка..."), "playing": True})
            self.plugin._force_broadcast_until[target] = time.time() + 5.0
        elif cmd == "set_volume":
            try:
                v_float = float(val) / 100.0
                payload_data = {"command": "setVolume", "volume": v_float}
                self.plugin.states[target]["volume"] = int(float(val))
                self.plugin._force_broadcast_until[target] = time.time() + 3.0
            except: pass
        elif cmd == "seek":
            try:
                pos = float(val)
                payload_data = {"command": "rewind", "position": pos}
                self.plugin.states[target]["progress"] = pos
                self.plugin._force_broadcast_until[target] = time.time() + 3.0
            except: pass
        elif cmd == "sync_track":
            if data and isinstance(data, dict):
                track_id = data.get("track_id")
                if track_id:
                    self.plugin.states[target]["track_id"] = track_id
                    await self.plugin.emit_event("track_changed", {"device_id": target, "track_id": track_id})
            return
            
        await self.plugin.broadcaster.push_state()
        if payload_data:
            full_payload = {
                "conversationToken": self.plugin.devices[target]["glagol_token"],
                "id": str(uuid.uuid4()),
                "sentTime": int(round(time.time() * 1000)),
                "payload": payload_data
            }
            await self.plugin.cmd_queues[target].put(full_payload)
            
            async def delayed_request():
                await asyncio.sleep(0.5)
                await monitor_request_state(self.plugin, target)
            asyncio.create_task(delayed_request())
