import asyncio
import psutil
from plugin_engine.base_plugin import BasePlugin

class Plugin(BasePlugin):
    """
    Пример унифицированного плагина v2.
    Заменяет старый жестко зашитый `_hal_loop`.
    """
    def __init__(self, plugin_id: str):
        super().__init__(plugin_id)
        self._loop_task: asyncio.Task | None = None
        self._last_cpu_times = psutil.cpu_times()

    async def on_start(self):
        self.log("SysInfo started. Launching monitoring task...")
        self._loop_task = asyncio.create_task(self._monitoring_loop())

    async def on_stop(self):
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        self.log("SysInfo stopped.")

    async def handle_command(self, action: str, data: any):
        """Здесь мы обрабатываем команды от UI"""
        self.log(f"Received command: {action} with data: {data}")
        if action == "force_update":
            await self._update_stats()

    async def _monitoring_loop(self):
        """Асинхронный цикл сбора статистики (не блокирует другие плагины!)"""
        try:
            while True:
                await self._update_stats()
                await asyncio.sleep(2.0) # Отдыхаем 2 секунды
        except asyncio.CancelledError:
            self.log("Monitoring loop cancelled.")

    async def _update_stats(self):
        current_cpu_times = psutil.cpu_times()
        t1_all = sum(self._last_cpu_times)
        t2_all = sum(current_cpu_times)
        t1_idle = self._last_cpu_times.idle
        t2_idle = current_cpu_times.idle
        self._last_cpu_times = current_cpu_times
        
        all_delta = t2_all - t1_all
        if all_delta > 0:
            idle_delta = t2_idle - t1_idle
            cpu = max(0.0, min(100.0, (1.0 - (idle_delta / all_delta)) * 100.0))
        else:
            cpu = 0.0

        ram = psutil.virtual_memory()
        
        state = {
            "cpu_load": cpu,
            "ram_percent": ram.percent,
            "ram_used_gb": round(ram.used / (1024**3), 2),
            "ram_total_gb": round(ram.total / (1024**3), 2)
        }
        
        # Стандартный метод BasePlugin для рассылки состояния клиентам
        await self.emit_state(state)
