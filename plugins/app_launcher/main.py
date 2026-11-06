import os
import asyncio
import subprocess
from plugin_engine.base_plugin import BasePlugin
from core.event_bus import event_bus

class Plugin(BasePlugin):
    """
    Плагин для запуска приложений на ПК.
    """
    def __init__(self, plugin_id: str):
        super().__init__(plugin_id)

    async def on_start(self):
        self.log("App Launcher started.")
        # Подписываемся на события от GUI (например, выбор файла)
        event_bus.subscribe("plugin_custom_event", self._on_custom_event)
        
        # Обновляем иконки и рассылаем состояние
        asyncio.create_task(self._auto_update_icons())
        await self._emit_launcher_state()

    async def _on_custom_event(self, data):
        """Обработка кастомных событий, например от GUI моста."""
        if data.get("plugin_id") != self.plugin_id:
            return
            
        event = data.get("event")
        payload = data.get("data")
        
        if event == "file_selected":
            # Важно: игнорируем события, которые мы сами уже обработали (в которых есть иконка)
            # иначе возникнет бесконечная рекурсия
            if payload.get("icon"):
                return

            path = payload.get("path")
            label = payload.get("label")
            self.log(f"File selected via GUI bridge: {path}")
            
            # Извлекаем иконку сразу, чтобы показать её в GUI
            icon_b64 = await asyncio.to_thread(self._extract_icon, path)
            
            # Отправляем событие обратно на UI (Android/Web), чтобы заполнить поля
            await self.emit_event("file_selected", {
                "path": path, 
                "label": label,
                "icon": icon_b64
            })

    async def _request_browse_dialog(self):
        """Запрашивает открытие диалога выбора файла у главного GUI процесса."""
        await event_bus.emit("request_file_dialog", {
            "plugin_id": self.plugin_id,
            "title": "Выберите приложение для добавления"
        })
        return None # Результат придет асинхронно через событие 'file_selected'

    async def _emit_launcher_state(self):
        config = self.get_config()
        buttons = []
        for widget in config.get("widgets", []):
            if widget.get("type") == "button_group":
                buttons = widget.get("buttons", [])
                break
        await self.emit_state({"buttons": buttons})

    async def on_stop(self):
        self.log("App Launcher stopped.")
        pass

    async def _auto_update_icons(self):
        config = self.get_config()
        changed = False
        for widget in config.get("widgets", []):
            if widget.get("type") == "button_group":
                for btn in widget.get("buttons", []):
                    # Если иконка не установлена или это просто текстовое имя иконки (не base64)
                    icon = btn.get("icon", "")
                    if not icon or (len(icon) < 50 and icon != "Default"):
                        icon_b64 = await asyncio.to_thread(self._extract_icon, btn.get("data"))
                        if icon_b64:
                            btn["icon"] = icon_b64
                            changed = True
        if changed:
            self.save_config(config)
            await self._emit_launcher_state()

    def _extract_icon(self, path: str):
        try:
            import sys
            import shutil
            import base64
            from PySide6.QtWidgets import QApplication, QFileIconProvider
            from PySide6.QtCore import QFileInfo, QBuffer, QIODevice
            from PySide6.QtGui import QIcon, QPixmap

            # Если путь не абсолютный, пробуем найти его в системе
            full_path = path
            if not os.path.isabs(path):
                found = shutil.which(path)
                if found:
                    full_path = found
                else:
                    # Пробуем стандартные места для Windows
                    common_paths = [
                        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), path),
                        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), path),
                        os.path.join(os.environ.get("LocalAppData", ""), "Programs", path)
                    ]
                    for p in common_paths:
                        if os.path.exists(p):
                            full_path = p
                            break
                        if os.path.exists(p + ".exe"):
                            full_path = p + ".exe"
                            break

            if not os.path.exists(full_path):
                return None

            # Нужен экземпляр QApplication (он обычно уже есть в процессе GUI)
            app = QApplication.instance()
            if app is None:
                # Если запускаем без GUI (только сервер), создаем временный
                app = QApplication(sys.argv)

            info = QFileInfo(full_path)
            provider = QFileIconProvider()
            icon = provider.icon(info)
            
            # Извлекаем пиксели в высоком разрешении (256x256)
            pixmap = icon.pixmap(256, 256)
            if pixmap.isNull():
                # Если 256 нет, пробуем 128
                pixmap = icon.pixmap(128, 128)
            
            if pixmap.isNull():
                return None

            buffer = QBuffer()
            buffer.open(QIODevice.WriteOnly)
            pixmap.save(buffer, "PNG")
            b64_data = base64.b64encode(buffer.data().data()).decode()
            
            return f"data:image/png;base64,{b64_data}"
        except Exception as e:
            # self.log(f"Icon extraction failed for {path}: {e}", 20)
            return None

    async def handle_command(self, action: str, data: any):
        if action == "launch":
            app_path = None
            if isinstance(data, dict):
                app_path = data.get("path") or data.get("value") or data.get("data")
            else:
                app_path = data
                
            # Если данные пришли в виде строки "{path=...}" (строковое представление Java Map)
            if isinstance(app_path, str) and app_path.startswith("{") and "=" in app_path:
                import re
                match = re.search(r"path=([^,}]+)", app_path) or re.search(r"value=([^,}]+)", app_path) or re.search(r"data=([^,}]+)", app_path)
                if match:
                    app_path = match.group(1).strip()
                else:
                    # Если регулярка не сработала, пробуем грубо очистить
                    app_path = app_path.split("=")[-1].rstrip("}")
                
            # Извлекаем список кнопок из конфигурации для проверки кастомных макро-действий
            config = self.get_config()
            buttons = []
            for widget in config.get("widgets", []):
                if widget.get("type") == "button_group":
                    buttons = widget.get("buttons", [])
                    break
                    
            # Ищем кнопку в конфигурации по совпадению очищенного пути или названия
            button = None
            if app_path:
                for btn in buttons:
                    if btn.get("data") == app_path or btn.get("label") == app_path:
                        button = btn
                        break
                        
            # Определяем тип макро-действия (по умолчанию 'launch' для обратной совместимости)
            btn_action_type = button.get("action", "launch") if button else "launch"
            
            self.log(f"Triggering macro: {app_path} (Type: {btn_action_type})")
            if app_path:
                if btn_action_type == "hotkey":
                    await asyncio.to_thread(self._send_hotkey, app_path)
                elif btn_action_type == "command":
                    await asyncio.to_thread(self._run_shell_command, app_path)
                elif btn_action_type == "media":
                    await asyncio.to_thread(self._send_media_key, app_path)
                elif btn_action_type == "system":
                    await asyncio.to_thread(self._execute_system_action, app_path)
                else:
                    # Стандартный запуск файла или ярлыка
                    await asyncio.to_thread(self._launch_app, app_path)
            else:
                self.log("Launch aborted: No path provided", 30)
            
        elif action == "browse_file":
            # Теперь это асинхронный запрос к GUI
            await self._request_browse_dialog()

        elif action == "add_app":
            config = self.get_config()
            app_path = data.get("path", "")
            btn_action = data.get("action", "launch")
            
            # Пытаемся достать иконку автоматически только для стандартного запуска приложений
            icon_b64 = None
            if btn_action == "launch":
                icon_b64 = await asyncio.to_thread(self._extract_icon, app_path)
            
            # Подбираем красивую дефолтную иконку в зависимости от типа макроса
            default_icons = {
                "launch": "AppWindow",
                "hotkey": "Terminal",
                "command": "Code",
                "media": "Music",
                "system": "Lock"
            }
            
            new_button = {
                "label": data.get("label", "New Macro"),
                "action": btn_action,
                "data": app_path,
                "icon": icon_b64 or data.get("icon") or default_icons.get(btn_action, "AppWindow")
            }
            
            for widget in config.get("widgets", []):
                if widget.get("type") == "button_group":
                    widget.setdefault("buttons", []).append(new_button)
                    break
            
            self.save_config(config)
            await self._emit_launcher_state()
            await self.emit_event("config_updated", {"success": True})

        elif action == "remove_app":
            # data может быть строкой или словарем {"value": "Label"} из-за особенностей сокет-хендлера
            label = data.get("value") if isinstance(data, dict) else data
            config = self.get_config()
            removed = False
            for widget in config.get("widgets", []):
                if widget.get("type") == "button_group":
                    original_count = len(widget.get("buttons", []))
                    widget["buttons"] = [b for b in widget["buttons"] if b.get("label") != label]
                    if len(widget["buttons"]) < original_count:
                        removed = True
            
            if removed:
                self.save_config(config)
                self.log(f"Removed app: {label}")
                await self._emit_launcher_state()
                await self.emit_event("config_updated", {"success": True})

        elif action == "move_app":
            # data: {"label": "Name", "direction": "up"|"down"}
            label = data.get("label")
            direction = data.get("direction")
            config = self.get_config()
            
            for widget in config.get("widgets", []):
                if widget.get("type") == "button_group":
                    buttons = widget.get("buttons", [])
                    idx = next((i for i, b in enumerate(buttons) if b.get("label") == label), -1)
                    if idx != -1:
                        if direction == "up" and idx > 0:
                            buttons[idx], buttons[idx-1] = buttons[idx-1], buttons[idx]
                        elif direction == "down" and idx < len(buttons) - 1:
                            buttons[idx], buttons[idx+1] = buttons[idx+1], buttons[idx]
                        
                        self.save_config(config)
                        await self._emit_launcher_state()
                        await self.emit_event("config_updated", {"success": True})
                    break

        elif action == "reorder_apps":
            # data: {"labels": ["Name1", "Name2", ...]}
            new_labels = data.get("labels", [])
            config = self.get_config()
            
            for widget in config.get("widgets", []):
                if widget.get("type") == "button_group":
                    current_buttons = widget.get("buttons", [])
                    # Создаем мапу для быстрого доступа
                    btn_map = {b.get("label"): b for b in current_buttons}
                    # Перестраиваем список в новом порядке
                    new_buttons = []
                    for label in new_labels:
                        if label in btn_map:
                            new_buttons.append(btn_map[label])
                    
                    # Добавляем те, что могли потеряться (на всякий случай)
                    for b in current_buttons:
                        if b.get("label") not in new_labels:
                            new_buttons.append(b)
                            
                    widget["buttons"] = new_buttons
                    self.save_config(config)
                    await self._emit_launcher_state()
                    await self.emit_event("config_updated", {"success": True})
                    break

        elif action == "update_settings":
            # Вызывается при сохранении настроек через общую панель управления
            self.log("Settings updated via API. Refreshing launcher state...")
            await self._emit_launcher_state()
            
        else:
            self.log(f"Unknown action: {action}")

    def _launch_app(self, path: str):
        try:
            # os.startfile — самый надежный способ на Windows запустить что угодно 
            # (exe, ссылку, папку, команду из PATH)
            os.startfile(path)
            self.log(f"Successfully launched: {path}")
        except Exception as e:
            self.log(f"Failed to launch {path}: {e}", level=30) # WARNING level
            
            # Попытка запустить через shell, если startfile не сработал
            try:
                subprocess.Popen(path, shell=True, creationflags=0x08000000)
                self.log(f"Launched via shell: {path}")
            except Exception as e2:
                self.log(f"Second attempt failed: {e2}", level=40) # ERROR level

    def _send_hotkey(self, keys_str: str):
        try:
            import ctypes
            import time
            
            parts = [p.strip().lower() for p in keys_str.split("+")]
            
            # Таблица Virtual Key кодов
            VK_CODES = {
                'ctrl': 0x11, 'control': 0x11,
                'shift': 0x10,
                'alt': 0x12,
                'win': 0x5B, 'super': 0x5B,
                'enter': 0x0D, 'return': 0x0D,
                'esc': 0x1B, 'escape': 0x1B,
                'space': 0x20,
                'tab': 0x09,
                'backspace': 0x08,
                'delete': 0x2E,
                'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73, 'f5': 0x74, 'f6': 0x75,
                'f7': 0x76, 'f8': 0x77, 'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
                'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28,
            }
            
            vk_inputs = []
            for p in parts:
                if p in VK_CODES:
                    vk_inputs.append(VK_CODES[p])
                elif len(p) == 1:
                    vk_inputs.append(ord(p.upper()))
                    
            if not vk_inputs:
                self.log(f"No valid keys found in: {keys_str}", level=30)
                return
                
            # Имитируем нажатие
            for vk in vk_inputs:
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            
            time.sleep(0.05)
            
            # Отпускаем клавиши в обратном порядке
            for vk in reversed(vk_inputs):
                ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
                
            self.log(f"Hotkey executed successfully: {keys_str}")
        except Exception as e:
            self.log(f"Failed to execute hotkey {keys_str}: {e}", level=40)

    def _run_shell_command(self, cmd: str):
        try:
            # Запускаем команду скрытно в фоне
            subprocess.Popen(cmd, shell=True, creationflags=0x08000000)
            self.log(f"Command executed silently: {cmd}")
        except Exception as e:
            self.log(f"Failed to execute command {cmd}: {e}", level=40)

    def _send_media_key(self, action: str):
        try:
            import ctypes
            VK_MEDIA = {
                'play': 0xB3, 'play_pause': 0xB3,
                'next': 0xB0,
                'prev': 0xB1,
                'stop': 0xB2,
                'mute': 0xAD, 'volume_mute': 0xAD,
                'volume_down': 0xAE,
                'volume_up': 0xAF
            }
            key = action.strip().lower()
            if key in VK_MEDIA:
                vk = VK_MEDIA[key]
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
                self.log(f"Media event triggered: {key}")
            else:
                self.log(f"Unknown media action: {key}", level=30)
        except Exception as e:
            self.log(f"Failed to send media key {action}: {e}", level=40)

    def _execute_system_action(self, action: str):
        try:
            import ctypes
            act = action.strip().lower()
            if act == "lock":
                ctypes.windll.user32.LockWorkStation()
                self.log("System locked successfully.")
            elif act == "sleep":
                # Перевод Windows в режим сна без гибернации
                ctypes.windll.PowrProf.SetSuspendState(0, 1, 0)
                self.log("System put to sleep successfully.")
            elif act == "mute_mic":
                # Переключение мута микрофона через нативный Windows PowerShell CoreAudio
                ps_cmd = "Set-AudioDevice -Recording -Mute (! (Get-AudioDevice -Recording).Mute)"
                subprocess.Popen(
                    ["powershell", "-Command", ps_cmd],
                    shell=True,
                    creationflags=0x08000000
                )
                self.log("Microphone mute toggled.")
            else:
                self.log(f"Unknown system action: {act}", level=30)
        except Exception as e:
            self.log(f"Failed to execute system action {action}: {e}", level=40)
