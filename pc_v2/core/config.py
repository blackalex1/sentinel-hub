import json
import os
from typing import List, Optional, Any
from pydantic import BaseModel, Field

import sys

# Определяем базовую директорию
if getattr(sys, 'frozen', False):
    # Если запущено как EXE (PyInstaller)
    # Директория, где лежит сам .exe файл
    BASE_DIR = os.path.dirname(sys.executable)
    # Директория, где лежат распакованные ресурсы (web, plugins)
    BUNDLE_DIR = sys._MEIPASS 
else:
    # Если запущено как скрипт
    # BASE_DIR - корень проекта
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    BUNDLE_DIR = os.path.join(BASE_DIR, "pc_v2")

DB_PATH = os.path.join(BASE_DIR, "database.db")

from core.database import SettingsDB

import uuid
import hashlib
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2

class MasterConfig(BaseModel):
    hostname: str = "MonitHome PC"
    os: str = "windows"
    language: str = "ru"
    theme_color: str = "0xFF22C55E"
    active_plugins: List[str] = [
        "sys_info", "system_stats", "yandex_lyrics", 
        "yandex_station", "pc_system", "pc_media", "pc_disks"
    ]
    trusted_tokens: List[str] = []
    server_uuid: str = "" # Уникальный ID сервера
    autostart: bool = False

class ConfigManager:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self.db = SettingsDB(self.db_path)
        
        # Генерируем уникальный ключ шифрования для этой машины
        self._encryption_key = self._derive_machine_key()
        
        # 1. Загружаем основные настройки
        self.config = self._load_master_config()
        
        # 2. Токен для GUI
        self.gui_token = self._setup_gui_token()

    def _derive_machine_key(self) -> bytes:
        """Генерирует уникальный 32-байтный ключ на основе ID машины"""
        # Используем MAC-адрес и системные данные как соль
        machine_id = str(uuid.getnode())
        salt = b"MonitHome_Secure_Salt_2024"
        # PBKDF2 делает перебор ключа крайне сложным
        return PBKDF2(machine_id, salt, dkLen=32, count=1000)

    def _encrypt(self, plaintext: str) -> bytes:
        """Шифрование строки в AES-GCM"""
        cipher = AES.new(self._encryption_key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode('utf-8'))
        # Сохраняем nonce + tag + ciphertext вместе
        return cipher.nonce + tag + ciphertext

    def _decrypt(self, encrypted_data: bytes) -> Optional[str]:
        """Расшифровка данных"""
        try:
            nonce = encrypted_data[:16]
            tag = encrypted_data[16:32]
            ciphertext = encrypted_data[32:]
            cipher = AES.new(self._encryption_key, AES.MODE_GCM, nonce=nonce)
            decrypted = cipher.decrypt_and_verify(ciphertext, tag)
            return decrypted.decode('utf-8')
        except Exception as e:
            print(f"[ConfigManager] Decryption failed: {e}")
            return None

    def set_secret(self, key: str, value: str):
        """Зашифровать и сохранить секрет в БД"""
        encrypted = self._encrypt(value)
        self.db.set_raw_secret(key, encrypted)

    def get_secret(self, key: str, default: Any = None) -> Any:
        """Получить и расшифровать секрет из БД"""
        raw = self.db.get_raw_secret(key)
        if raw:
            decrypted = self._decrypt(raw)
            return decrypted if decrypted is not None else default
        return default

    def _load_master_config(self) -> MasterConfig:
        """Загрузка глобальных настроек из БД с фолбэком на дефолты"""
        defaults = MasterConfig().model_dump()
        stored = {}
        
        # Пытаемся достать каждое поле из БД
        for key in defaults.keys():
            val = self.db.get_global(key)
            if val is not None:
                stored[key] = val
        
        # Специальная обработка для UUID (он должен быть всегда)
        if not stored.get("server_uuid"):
            new_uuid = str(uuid.uuid4())
            self.db.set_global("server_uuid", new_uuid)
            stored["server_uuid"] = new_uuid
            print(f"[ConfigManager] Generated new Server UUID: {new_uuid}")

        # Если база пустая, попробуем импортировать из старого master_config.json (для миграции)
        old_config_path = os.path.join(BASE_DIR, "master_config.json")
        if len(stored) <= 1 and os.path.exists(old_config_path):
            try:
                with open(old_config_path, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                    for k, v in old_data.items():
                        if k in defaults:
                            self.db.set_global(k, v)
                            stored[k] = v
                print(f"[ConfigManager] Migrated settings from master_config.json to DB")
            except: pass

        # Объединяем дефолты и сохраненное
        final_data = {**defaults, **stored}
        return MasterConfig(**final_data)

    def _setup_gui_token(self) -> str:
        """Получение или генерация токена доступа для GUI"""
        import secrets
        
        token = self.db.get_global("gui_token")
        if not token:
            token = secrets.token_hex(16)
            self.db.set_global("gui_token", token)
            
        return token

    def save(self):
        """Сохранение текущего MasterConfig в БД"""
        data = self.config.model_dump()
        for k, v in data.items():
            self.db.set_global(k, v)

    def get(self) -> MasterConfig:
        return self.config

    # --- РАБОТА С ПЛАГИНАМИ ---

    def get_plugin_config(self, plugin_id: str, default_json_config: dict) -> dict:
        """
        Возвращает конфиг плагина: Базовый JSON + Оверрайды из БД.
        """
        db_settings = self.db.get_plugin_settings(plugin_id)
        if db_settings:
            # Накладываем оверрайды из БД на дефолты из JSON
            # Это позволяет добавлять новые поля в JSON при обновлениях,
            # и они будут подтягиваться автоматически.
            merged = {**default_json_config, **db_settings}
            return merged
        return default_json_config

    def save_plugin_config(self, plugin_id: str, settings: dict):
        """Сохраняет настройки плагина в БД (слияние с текущими оверрайдами)"""
        current_db_settings = self.db.get_plugin_settings(plugin_id) or {}
        # Сливаем текущие оверрайды с новыми (новые заменяют старые)
        merged = {**current_db_settings, **settings}
        self.db.set_plugin_settings(plugin_id, merged)

# Global instance
config_manager = ConfigManager()
