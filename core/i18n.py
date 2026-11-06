import os
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("I18n")

class I18nManager:
    """
    Централизованный менеджер локализации.
    Объединяет переводы ядра и всех активных плагинов.
    """
    _instance = None

    def __init__(self):
        self.current_lang = "ru"
        self._translations = {}
        self._plugin_translations = {} # {plugin_id: {lang: data}}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_language(self, lang: str):
        if self.current_lang != lang:
            logger.info(f"Language changed to: {lang}")
            self.current_lang = lang
            self._translations = {} # Сброс кэша

    def get_translations(self, lang: Optional[str] = None) -> Dict[str, str]:
        """Возвращает объединенный словарь переводов для указанного языка"""
        target_lang = lang or self.current_lang
        
        # 1. Загружаем базовые переводы ядра
        from core.config import BUNDLE_DIR
        core_lang_path = os.path.join(BUNDLE_DIR, "web", "languages", f"{target_lang}.json")
        
        full_translations = {}
        if os.path.exists(core_lang_path):
            try:
                with open(core_lang_path, "r", encoding="utf-8") as f:
                    full_translations = json.load(f)
            except Exception as e:
                logger.error(f"Error loading core translations ({target_lang}): {e}")

        # 2. Собираем переводы от всех активных плагинов
        from plugin_engine.manager import plugin_manager
        for p_id, plugin in plugin_manager.active_plugins.items():
            plugin_locales = self._load_plugin_locales(p_id, target_lang)
            if plugin_locales:
                # Добавляем префикс к ключам плагина, чтобы избежать коллизий? 
                # Или просто мерджим? В MonitHome ключи обычно уникальны.
                full_translations.update(plugin_locales)
        
        return full_translations

    def translate(self, key: str, default: Optional[str] = None) -> str:
        if not self._translations:
            self._translations = self.get_translations()
        return self._translations.get(key, default or key)

    def _load_plugin_locales(self, plugin_id: str, lang: str) -> Dict[str, str]:
        """Загрузка локалей конкретного плагина"""
        from plugin_engine.manager import plugin_manager
        plugin = plugin_manager.active_plugins.get(plugin_id)
        if not plugin:
            return {}
        
        # Находим путь к папке плагина
        import sys
        try:
            plugin_dir = os.path.dirname(sys.modules[plugin.__module__].__file__)
            locale_path = os.path.join(plugin_dir, "locales", f"{lang}.json")
            
            if os.path.exists(locale_path):
                with open(locale_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading locales for plugin {plugin_id}: {e}")
            
        return {}

# Global helper
def t(key: str, default: Optional[str] = None) -> str:
    return I18nManager.get_instance().translate(key, default)
