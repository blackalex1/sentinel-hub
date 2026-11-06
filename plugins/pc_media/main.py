import asyncio
import sys
import os
import json
import base64
import traceback
from plugin_engine.base_plugin import BasePlugin
from core.event_bus import event_bus

from .volume_utils import VolumeManager, press_media_key

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3

class Plugin(BasePlugin):
    """
    Плагин мониторинга PC Media (pc_media v2).
    Использует asyncio.create_subprocess_exec для асинхронного чтения вывода media_scanner.py.
    """
    def __init__(self, plugin_id: str):
        super().__init__(plugin_id)
        self.volume_manager = VolumeManager()
        self._media_info = {"title": "", "artist": "", "playing": False, "cover": None, "duration": 0.0, "progress": 0.0, "volume": 0, "mute": False, "status": "initializing"}
        self._scanner_task: asyncio.Task | None = None
        self._process = None

    async def on_start(self):
        config = self.get_config()
        enabled = config.get("pc_enabled", True)
        if enabled:
            await self.start_scanner()
        else:
            self.log("pc_media is disabled by configuration. Deferring scanner startup (lazy start).")

    async def on_stop(self):
        await self.stop_scanner()
        self.log("pc_media stopped.")

    async def start_scanner(self):
        if not self._scanner_task:
            self.log("Spawning media scanner process...")
            self._scanner_task = asyncio.create_task(self._media_worker())

    async def stop_scanner(self):
        if self._scanner_task:
            self._scanner_task.cancel()
            self._scanner_task = None
        if self._process:
            try:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    self._process.kill()
            except: pass
            self._process = None
        self._media_info["status"] = "offline"

    async def _media_worker(self):
        python_exe = sys.executable
        # Для EXE используем путь относительно исполняемого файла или временной папки
        base_dir = os.path.dirname(os.path.abspath(__file__))
        scanner_path = os.path.join(base_dir, "media_scanner.py")
        
        while True:
            try:
                self.log(f"Starting subprocess: {scanner_path}")
                # Флаг для скрытия окна консоли на Windows (CREATE_NO_WINDOW)
                creationflags = 0x08000000 if sys.platform == "win32" else 0
                
                self._process = await asyncio.create_subprocess_exec(
                    python_exe, scanner_path,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    creationflags=creationflags
                )
                
                while True:
                    line = await self._process.stdout.readline()
                    if not line:
                        break # EOF
                        
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    if not line_str: continue
                    
                    try:
                        info = json.loads(line_str)
                        if "log" in info and len(info) == 1:
                            # self.log(f"Scanner: {info['log']}")
                            continue
                        
                        if "cover_event" in info:
                            await self._send_cover_from_file(info.get("title", ""))
                            continue
                            
                        # Сравниваем, чтобы понять, новый ли это трек
                        is_new_track = (info.get("title") != self._media_info.get("title") or 
                                       (info.get("artist") is not None and info.get("artist") != self._media_info.get("artist")))
                        
                        self._media_info.update(info)
                        
                        if is_new_track:
                            self.log(f"Now playing: {info.get('title')} - {info.get('artist')}")
                        
                        await self._emit_stats()
                        
                    except json.JSONDecodeError:
                        self.log(f"JSON Error: {line_str[:50]}...")
                    except Exception as e:
                        self.log(f"Parse error: {e}")
                        
            except asyncio.CancelledError:
                self.log("Scanner worker cancelled.")
                if self._process:
                    try:
                        self._process.terminate()
                    except: pass
                break
            except Exception as e:
                self.log(f"Scanner error: {e}")
                
            self.log("Scanner process died, restarting in 2s...")
            await asyncio.sleep(2.0)

    async def _emit_stats(self):
        stats = {k: v for k, v in self._media_info.items()}
        stats["duration"] = float(stats.get("duration", 0.0))
        stats["progress"] = float(stats.get("progress", 0.0))
        stats["volume"] = int(stats.get("volume", 0))
        stats["device_name"] = self.i18n("pc_media_device", "Этот компьютер")
        await self.emit_state(stats)

    async def _send_cover_from_file(self, title: str):
        try:
            cover_path = os.path.join(os.path.dirname(__file__), "cover.jpg")
            if os.path.exists(cover_path):
                import shutil
                import time
                from core.config import BUNDLE_DIR
                from network.discovery import DiscoveryManager
                
                # Копируем файл в статику веб-сервера
                web_dir = os.path.join(BUNDLE_DIR, "web")
                if not os.path.exists(web_dir):
                    os.makedirs(web_dir)
                    
                dest_path = os.path.join(web_dir, "cover.jpg")
                def copy_file():
                    try:
                        shutil.copy2(cover_path, dest_path)
                    except Exception as e:
                        self.log(f"Failed to copy cover: {e}", 30)
                await asyncio.to_thread(copy_file)
                
                # Строим абсолютную ссылку
                try:
                    local_ip = DiscoveryManager(port=5000).get_local_ip()
                except Exception:
                    local_ip = "127.0.0.1"
                    
                cover_url = f"https://{local_ip}:5000/static/cover.jpg?t={int(time.time())}"
                self._media_info["cover"] = cover_url
                self.log(f"Sending cover for: {title} via URL: {cover_url}")
                await self.emit_event("cover", {"cover": cover_url, "title": title})
                await self._emit_stats()
        except Exception as e:
            self.log(f"Cover error: {e}", 40)

    async def handle_command(self, action: str, data: any):
        if action == "handle_wizard":
            enabled = "pc_media_enabled" in data
            self.save_config({"pc_enabled": enabled})
            if enabled:
                await self.start_scanner()
            else:
                await self.stop_scanner()
            return

        if action.startswith("set_volume:"):
            try:
                level = int(action.split(":")[1])
                await asyncio.to_thread(self.volume_manager.set_volume, level)
            except: pass
        elif action == "toggle_mute":
            current_mute = self._media_info.get("mute", False)
            await asyncio.to_thread(self.volume_manager.set_mute, not current_mute)
        elif action == "next":
            press_media_key(VK_MEDIA_NEXT_TRACK)
        elif action == "prev":
            press_media_key(VK_MEDIA_PREV_TRACK)
        elif action == "play_pause":
            press_media_key(VK_MEDIA_PLAY_PAUSE)
        elif action.startswith("seek:"):
            try:
                pos = float(action.split(":")[1])
                if self._process and self._process.stdin:
                    cmd_str = json.dumps({"action": "seek", "position": pos}) + "\n"
                    self._process.stdin.write(cmd_str.encode())
                    await self._process.stdin.drain()
                    self.log(f"Sent seek command to scanner: {pos}s")
            except Exception as e:
                self.log(f"Seek error: {e}")
