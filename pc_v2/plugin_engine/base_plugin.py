import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict
import logging
import sys
from core.event_bus import event_bus

class BasePlugin(ABC):
    """
    Единый стандарт (Унификация) для всех плагинов v2.
    Все плагины должны наследоваться от этого класса.
    """
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        self.logger = logging.getLogger(f"Plugin.{plugin_id}")
        self._is_running = False
        self.needs_elevation = False # Флаг: нужны ли права админа прямо сейчас
        self.elevation_active = False # Флаг: права админа успешно получены и активны
        self._tasks = set()

    async def start(self):
        """Внутренний метод запуска. Не переопределять в плагинах."""
        if self._is_running:
            return
        
        self.log("Starting...")
        try:
            # Даем плагину 10 секунд на инициализацию (важно для сетевых плагинов)
            await asyncio.wait_for(self.on_start(), timeout=10.0)
            self._is_running = True
            self.log("Started successfully.")
        except asyncio.TimeoutError:
            self.log("on_start timed out after 10s", level=logging.ERROR)
            await self.stop() # Пытаемся очистить ресурсы
        except Exception as e:
            self.log(f"Failed to start: {e}", level=logging.ERROR)
            await self.stop()

    async def stop(self):
        """Внутренний метод остановки. Не переопределять в плагинах."""
        if not self._is_running:
            return
        
        self.log("Stopping...")
        
        # 1. Вызываем пользовательский метод остановки
        try:
            await asyncio.wait_for(self.on_stop(), timeout=2.0)
        except asyncio.TimeoutError:
            self.log("on_stop timed out", level=logging.WARNING)
        except Exception as e:
            self.log(f"Error in on_stop: {e}", level=logging.ERROR)

        # 2. Отменяем все фоновые задачи, созданные через create_task
        if self._tasks:
            self.log(f"Cancelling {len(self._tasks)} tasks...")
            for task in self._tasks:
                if not task.done():
                    task.cancel()
            
            # Ждем завершения отмены (опционально, с таймаутом)
            try:
                await asyncio.wait_for(asyncio.gather(*self._tasks, return_exceptions=True), timeout=1.0)
            except:
                pass
            self._tasks.clear()

        self._is_running = False
        self.log("Stopped.")

    def create_task(self, coro):
        """Хелпер для запуска фоновых задач с автоматическим отслеживанием"""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    @abstractmethod
    async def on_start(self):
        """Вызывается при запуске плагина. Здесь нужно запускать фоновые таски."""
        pass

    @abstractmethod
    async def on_stop(self):
        """Вызывается при остановке плагина. Здесь нужно отменять таски и закрывать сокеты."""
        pass

    @abstractmethod
    async def handle_command(self, action: str, data: Any):
        """Обработка команд от UI (Android / Web)."""
        pass

    async def check_admin_requirement(self) -> bool:
        """
        Проверка: нужны ли плагину права админа прямо сейчас.
        Переопределяется в плагинах с requires_admin: "if_required".
        """
        return False

    # --- УТИЛИТЫ ДЛЯ ПЛАГИНОВ ---

    def log(self, message: str, level: int = logging.INFO):
        """Стандартное логирование для плагинов"""
        self.logger.log(level, message)

    async def emit_state(self, state: Dict[str, Any]):
        """Отправка обновленного состояния плагина."""
        # Добавляем флаги прав админа в состояние, чтобы UI знал, что показывать
        full_state = {
            **state, 
            "needs_elevation": self.needs_elevation,
            "elevation_active": self.elevation_active
        }
        await event_bus.emit("plugin_state_changed", {
            "plugin_id": self.plugin_id,
            "state": full_state
        })

    async def emit_event(self, event_name: str, data: Any, room: str = None):
        """Отправка специфичного события плагина."""
        await event_bus.emit("plugin_custom_event", {
            "plugin_id": self.plugin_id,
            "event": event_name,
            "data": data,
            "room": room
        })

    def get_config(self) -> Dict[str, Any]:
        """Возвращает конфигурацию плагина: Базовый JSON + Оверрайды из БД"""
        import os
        import json
        from core.config import config_manager
        
        # 1. Загружаем дефолты из JSON (шаблон)
        # Находим путь к файлу плагина
        plugin_dir = os.path.dirname(sys.modules[self.__module__].__file__)
        config_path = os.path.join(plugin_dir, "config.json")
        
        default_config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    default_config = json.load(f)
            except Exception as e:
                self.log(f"Error reading base config.json: {e}", level=logging.ERROR)
        
        # 2. Получаем финальный конфиг (дефолт + оверрайды из БД) через ConfigManager
        return config_manager.get_plugin_config(self.plugin_id, default_config)

    def save_config(self, new_config: Dict[str, Any]):
        """Сохраняет настройки плагина в базу данных"""
        from core.config import config_manager
        
        # Мы сохраняем переданный конфиг полностью как оверрайд в БД
        try:
            config_manager.save_plugin_config(self.plugin_id, new_config)
            self.log("Config saved to Database.")
            # Уведомляем систему, что конфиг плагина изменился (для рассылки ui_config)
            asyncio.create_task(event_bus.emit("ui_config_changed", {"plugin_id": self.plugin_id}))
        except Exception as e:
            self.log(f"Error saving config to DB: {e}", level=logging.ERROR)

    def get_secret(self, key: str, default: Any = None) -> Any:
        """Получить зашифрованный секрет из БД"""
        from core.config import config_manager
        return config_manager.get_secret(key, default)

    def set_secret(self, key: str, value: Any):
        """Зашифровать и сохранить секрет в БД"""
        from core.config import config_manager
        config_manager.set_secret(key, value)

    def i18n(self, key: str, default: str = None) -> str:
        """Локализация через центральный менеджер."""
        from core.i18n import I18nManager
        return I18nManager.get_instance().translate(key, default)
