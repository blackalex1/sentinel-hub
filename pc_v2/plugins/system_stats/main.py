import asyncio
import psutil
import platform
import socket
import os
import ctypes
import time
from typing import Dict, Any

from plugin_engine.base_plugin import BasePlugin
from .afterburner_reader import get_afterburner_stats
from core.event_bus import event_bus
from core.elevation import get_elevation_manager

class Plugin(BasePlugin):
    """
    Плагин сбора аппаратной статистики (system_stats v2).
    Использует централизованный ElevationManager для получения данных под админом.
    """
    def __init__(self, plugin_id: str):
        super().__init__(plugin_id)
        self._loop_task = None
        self._state = {
            "cpu": 0, "cpu_temp": 0, "ram_percent": 0, "ram_used": 0, "ram_total": 0,
            "gpu_load": 0, "gpu_temp": 0, "has_gpu": False, "gpu_name": "GPU",
            "hostname": socket.gethostname(), "os": platform.system()
        }
        self._cpu_name = None
        self._gpu_name = None
        self.needs_elevation = not (ctypes.windll.shell32.IsUserAnAdmin() != 0)
        self.elevation_active = False
        self._last_cpu_times = psutil.cpu_times()

    async def on_start(self):
        self.log("system_stats started.")
        self._loop_task = self.create_task(self._stats_loop())

    async def on_stop(self):
        if self._loop_task:
            self._loop_task.cancel()
        self.log("system_stats stopped.")

    async def handle_command(self, action: str, data: any):
        if action == "update_sensor_settings":
            self.save_config({"enabled_sensors": data})
            await self._rebuild_widgets_from_settings(data)
            await self._update_and_emit()
        elif action == "elevate":
            self.log("Manual elevation requested via GUI.")
            em = await get_elevation_manager()
            await em.request_elevation()
            await self._update_and_emit()

    async def check_admin_requirement(self) -> bool:
        return self.needs_elevation

    async def _stats_loop(self):
        try:
            while True:
                await self._update_and_emit()
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            self.log("Stats loop cancelled.")

    async def _update_and_emit(self):
        cfg = self.get_config()
        sensors = cfg.get("enabled_sensors", {})
        new_state = {}
        
        # RAM stats
        if sensors.get("ram", True):
            ram = psutil.virtual_memory()
            ram_used_gb = round(ram.used / (1024**3), 2)
            ram_total_gb = round(ram.total / (1024**3), 2)
            new_state.update({
                "ram_percent": ram.percent,
                "display_ram_percent": f"{ram.percent}%",
                "ram_used": ram_used_gb,
                "ram_total": ram_total_gb,
                "display_ram_combined": f"{ram.percent}% ({ram_used_gb}/{ram_total_gb} GB)"
            })

        # CPU load
        if sensors.get("cpu", True):
            current_cpu_times = psutil.cpu_times()
            t1_all = sum(self._last_cpu_times)
            t2_all = sum(current_cpu_times)
            t1_idle = self._last_cpu_times.idle
            t2_idle = current_cpu_times.idle
            self._last_cpu_times = current_cpu_times
            
            all_delta = t2_all - t1_all
            if all_delta > 0:
                idle_delta = t2_idle - t1_idle
                cpu_l = max(0.0, min(100.0, (1.0 - (idle_delta / all_delta)) * 100.0))
            else:
                cpu_l = 0.0
                
            new_state.update({"cpu": cpu_l, "display_cpu": f"{int(cpu_l)}%"})

        # Hardware stats (GPU, Temp)
        hw_stats = await self._fetch_hardware_stats()
        if hw_stats:
            new_state.update(hw_stats)
        else:
            # Preserve old data if helper is down
            for key in ["gpu_load", "gpu_temp", "cpu_temp", "display_gpu_load", "display_gpu_temp", "display_cpu_temp", "has_gpu", "gpu_name"]:
                if key in self._state:
                    new_state[key] = self._state[key]

        self._state = new_state
        await self.emit_state(self._state)
        try:
            event_bus.emit_sync("plugin_state_changed", {"plugin_id": self.plugin_id, "state": self._state})
        except: pass

    async def _fetch_hardware_stats(self) -> Dict[str, Any]:
        hw = {}
        cpu_t, gpu_l, gpu_t = 0, 0, 0
        has_gpu = False
        helper_data = None

        # Try Afterburner first
        ab_stats = get_afterburner_stats()
        if ab_stats:
            cpu_t = ab_stats.get('cpu_temp', 0)
            gpu_l = ab_stats.get('gpu_load', 0)
            gpu_t = ab_stats.get('gpu_temp', 0)
            self._gpu_name = ab_stats.get('gpu_name', self._gpu_name)
            has_gpu = True if self._gpu_name else (gpu_l > 0 or gpu_t > 0)

        # Try Unified Elevation Manager (Helper)
        if cpu_t == 0 or gpu_t == 0 or not has_gpu:
            em = await get_elevation_manager()
            helper_data = await em.get_stats()
            if helper_data:
                if cpu_t == 0: cpu_t = helper_data.get('cpu_temp', 0)
                if gpu_t == 0: gpu_t = helper_data.get('gpu_temp', 0)
                if gpu_l == 0: gpu_l = helper_data.get('gpu_load', 0)
                if helper_data.get('has_gpu'): has_gpu = True
                if not self._gpu_name:
                    self._gpu_name = helper_data.get('gpu_name')
                
                # Update elevation status
                is_admin_now = helper_data.get('is_admin', False) or (ctypes.windll.shell32.IsUserAnAdmin() != 0)
                if is_admin_now:
                    self.elevation_active = True
                    self.needs_elevation = False
                else:
                    self.elevation_active = False
                    self.needs_elevation = True

        hw.update({
            "cpu_temp": cpu_t, "display_cpu_temp": f"{int(cpu_t)}°C" if cpu_t else "N/A",
            "gpu_load": gpu_l, "display_gpu_load": f"{int(gpu_l)}%" if gpu_l else "0%",
            "gpu_temp": gpu_t, "display_gpu_temp": f"{int(gpu_t)}°C" if gpu_t else "N/A",
            "has_gpu": has_gpu or bool(self._gpu_name),
            "cpu_name": (helper_data.get('cpu_name') if helper_data else None) or self._cpu_name or "CPU",
            "gpu_name": self._gpu_name or "GPU"
        })
        self._cpu_name = hw["cpu_name"]
        return hw

    async def _rebuild_widgets_from_settings(self, sensors: dict):
        widgets = []
        if sensors.get("cpu_load", True):
            widgets.append({"id": "cpu_chart", "type": "chart", "label": "cpu_usage", "data_key": "cpu", "color": "#38bdf8", "icon": "cpu"})
        if sensors.get("cpu_temp", True):
            widgets.append({"id": "cpu_temp_chart", "type": "chart", "label": "cpu_temp", "data_key": "cpu_temp", "color": "#ef4444", "unit": "°C", "icon": "cpu"})
        if sensors.get("gpu_load", True):
            widgets.append({"id": "gpu_load_widget", "type": "stat", "label": "gpu_load", "data_key": "display_gpu_load", "icon": "gpu", "color": "#10b981"})
        if sensors.get("gpu_temp", True):
            widgets.append({"id": "gpu_temp_widget", "type": "stat", "label": "gpu_temp", "data_key": "display_gpu_temp", "icon": "gpu", "color": "#f59e0b"})
        if sensors.get("ram", True):
            widgets.append({"id": "ram_combined_widget", "type": "stat", "label": "ram_label", "data_key": "display_ram_combined", "icon": "ram", "color": "#8b5cf6"})
        
        self.save_config({"widgets": widgets, "enabled_sensors": sensors})
        await asyncio.sleep(0.1)
        await event_bus.emit("ui_config_changed", {"plugin_id": self.plugin_id})
