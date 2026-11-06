import asyncio
import logging
import importlib
import sys
import os
from typing import Dict, Any, Type
from plugin_engine.base_plugin import BasePlugin
from core.config import config_manager
from core.event_bus import event_bus

import ctypes
import json

logger = logging.getLogger("PluginManager")

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

class PluginManager:
    """
    Асинхронный менеджер жизненного цикла плагинов v2.
    Отвечает только за запуск, остановку и маршрутизацию команд к плагинам.
    """
    def __init__(self):
        self.active_plugins: Dict[str, BasePlugin] = {}

    async def pre_check_elevation(self):
        """
        Проверка необходимости повышения прав до старта сервера.
        Теперь мы не перезапускаем всё приложение автоматически.
        """
        return False

    async def initialize(self):
        """Считывает конфиг и запускает активные плагины"""
        cfg = config_manager.get()
        active_ids = cfg.active_plugins
        
        # Проверяем наличие директорий плагинов перед запуском
        from core.config import BUNDLE_DIR
        plugins_dir = os.path.join(BUNDLE_DIR, "plugins")
        
        existing_ids = []
        if os.path.exists(plugins_dir):
            existing_ids = [d for d in os.listdir(plugins_dir) if os.path.isdir(os.path.join(plugins_dir, d))]
        
        # Фильтруем список активных, оставляя только те, что реально есть на диске
        to_start = [p_id for p_id in active_ids if p_id in existing_ids]
        
        if len(to_start) != len(active_ids):
            logger.warning(f"Some active plugins are missing from disk: {set(active_ids) - set(to_start)}. Cleaning up config.")
            config_manager.config.active_plugins = to_start
            config_manager.save()
            
        logger.info(f"Initializing plugins: {to_start}")
        
        for p_id in to_start:
            await self.start_plugin(p_id)

    async def start_plugin(self, plugin_id: str):
        # Если плагин уже запущен, сначала останавливаем его
        if plugin_id in self.active_plugins:
            logger.info(f"Plugin {plugin_id} is already running. Stopping before reload...")
            await self.stop_plugin(plugin_id)

        try:
            module_name = f"plugins.{plugin_id}.main"
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
            
            module = importlib.import_module(module_name)
            plugin_class: Type[BasePlugin] = getattr(module, "Plugin")
            
            instance = plugin_class(plugin_id=plugin_id)
            
            # Ждем инициализации плагина
            await instance.start()
            
            if instance._is_running:
                self.active_plugins[plugin_id] = instance
                logger.info(f"Successfully initialized plugin: {plugin_id}")
            else:
                logger.error(f"Plugin {plugin_id} failed to start (check logs)")
                
        except Exception as e:
            logger.error(f"Failed to load plugin module {plugin_id}: {e}")

    async def stop_plugin(self, plugin_id: str):
        if plugin_id in self.active_plugins:
            instance = self.active_plugins.pop(plugin_id)
            try:
                await instance.stop()
                logger.info(f"Successfully stopped plugin: {plugin_id}")
            except Exception as e:
                logger.error(f"Error stopping plugin {plugin_id}: {e}")

    async def handle_command(self, plugin_id: str, action: str, data: Any):
        if plugin_id in self.active_plugins:
            instance = self.active_plugins[plugin_id]
            try:
                # Специальная команда на повышение прав
                if action == "request_elevation":
                    await self._elevate_plugin(instance)
                else:
                    # Выполняем команду с таймаутом, чтобы один плагин не вешал поток команд
                    asyncio.create_task(self._safe_handle_command(instance, action, data))
            except Exception as e:
                logger.error(f"Error preparing command {action} for {plugin_id}: {e}")
        else:
            logger.warning(f"Command '{action}' received for inactive plugin '{plugin_id}'")

    async def _safe_handle_command(self, instance: BasePlugin, action: str, data: Any):
        try:
            await asyncio.wait_for(instance.handle_command(action, data), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error(f"Command '{action}' for plugin '{instance.plugin_id}' timed out!")
        except Exception as e:
            logger.error(f"Error in plugin '{instance.plugin_id}' while handling '{action}': {e}")

    async def _elevate_plugin(self, plugin: BasePlugin):
        """Стандартная логика повышения прав для плагина"""
        logger.info(f"Elevation requested for plugin: {plugin.plugin_id}")
        # Плагин должен уметь обрабатывать команду 'elevate' самостоятельно, 
        # так как способ повышения прав (через helper или перезапуск) может отличаться.
        await plugin.handle_command("elevate", None)

    async def shutdown(self):
        tasks = [self.stop_plugin(p_id) for p_id in list(self.active_plugins.keys())]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

plugin_manager = PluginManager()
