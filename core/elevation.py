import asyncio
import logging
import os
import sys
import json
import time
import ctypes
import mmap
import subprocess
from typing import Dict, Any, Optional

logger = logging.getLogger("ElevationManager")

SHMEM_NAME = "Local\\MonitHomeSensors_V9"
SHMEM_SIZE = 16384

class ElevationManager:
    """
    Менеджер привилегированных операций и сбора системных данных.
    Управляет Helper-процессом и предоставляет данные плагинам.
    """
    _instance = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._helper_proc = None
        self._last_stats = {}
        self._last_update_time = 0
        self._running = False
        self._update_task = None

    @classmethod
    async def get_instance(cls):
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    async def start(self):
        if self._running:
            return
        self._running = True
        
        # Запускаем ОБЫЧНЫЙ хелпер при старте. 
        # Он не требует UAC и даст базовые данные (имена CPU/GPU).
        await self._start_helper(elevate=False)
        
        self._update_task = asyncio.create_task(self._monitor_loop())
        logger.info("Elevation Manager started with normal helper.")

    async def stop(self):
        self._running = False
        if self._update_task:
            self._update_task.cancel()
        await self._stop_helper()
        logger.info("Elevation Manager stopped.")

    async def get_stats(self) -> Dict[str, Any]:
        """Возвращает последние данные от хелпера"""
        # Если данные протухли (более 5 секунд), считаем их невалидными
        if time.time() - self._last_update_time > 5:
            return {}
        return self._last_stats

    async def execute_command(self, action: str, params: Dict[str, Any] = None):
        """Отправка привилегированной команды хелперу"""
        try:
            cmd = {"action": action, **(params or {})}
            data = json.dumps(cmd).encode('utf-8')
            data = data.ljust(1024, b'\x00')
            
            await asyncio.to_thread(self._write_cmd_shmem, data)
            logger.info(f"Command '{action}' sent to helper.")
        except Exception as e:
            logger.error(f"Failed to send command to helper: {e}")

    def _write_cmd_shmem(self, data: bytes):
        try:
            shm = mmap.mmap(-1, 1024, tagname="Local\\MonitHomeCommands_V9", access=mmap.ACCESS_WRITE)
            shm.write(data)
            shm.close()
        except Exception as e:
            logger.error(f"Error writing command to SHMEM: {e}")

    async def request_elevation(self):
        """Запуск хелпера с правами администратора"""
        await self._start_helper(elevate=True)

    async def _start_helper(self, elevate=False):
        try:
            # Сначала убиваем старый, если есть
            await self._stop_helper()
            await asyncio.sleep(0.5)

            from core.config import BUNDLE_DIR
            # Путь к хелперу (предполагаем, что он в plugins/system_stats/bin или рядом)
            # Для универсальности ищем в нескольких местах
            possible_paths = [
                os.path.join(BUNDLE_DIR, "plugins", "system_stats", "bin", "MonitHomeHelper.exe"),
                os.path.join(BUNDLE_DIR, "bin", "MonitHomeHelper.exe")
            ]
            
            helper_exe = None
            for p in possible_paths:
                if os.path.exists(p):
                    helper_exe = p
                    break
            
            if helper_exe:
                if elevate:
                    logger.info(f"Starting ADMIN helper: {helper_exe}")
                    ctypes.windll.shell32.ShellExecuteW(None, "runas", helper_exe, f"--parent-pid {os.getpid()}", None, 0)
                else:
                    logger.info(f"Starting normal helper: {helper_exe}")
                    subprocess.Popen([helper_exe, "--parent-pid", str(os.getpid())], creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                # Фолбэк на скрипт
                helper_py = os.path.join(BUNDLE_DIR, "plugins", "system_stats", "sensor_helper.py")
                if os.path.exists(helper_py):
                    logger.info(f"Helper EXE not found, using script: {helper_py}")
                    python_exe = sys.executable
                    args = f'"{helper_py}" --parent-pid {os.getpid()}'
                    verb = "runas" if elevate else None
                    ctypes.windll.shell32.ShellExecuteW(None, verb, python_exe, args, None, 0)
                else:
                    logger.error("Helper NOT FOUND anywhere!")
        except Exception as e:
            logger.error(f"Failed to start helper: {e}")

    async def _stop_helper(self):
        try:
            flags = 0x08000000 if os.name == 'nt' else 0
            subprocess.run(["taskkill", "/F", "/IM", "MonitHomeHelper.exe"], capture_output=True, creationflags=flags)
        except:
            pass

    async def _monitor_loop(self):
        """Петля чтения данных из Shared Memory"""
        while self._running:
            try:
                stats = await asyncio.to_thread(self._read_shmem)
                if stats:
                    self._last_stats = stats
                    self._last_update_time = time.time()
            except Exception as e:
                pass
            await asyncio.sleep(1)

    def _read_shmem(self) -> Optional[Dict[str, Any]]:
        try:
            shm = mmap.mmap(-1, SHMEM_SIZE, tagname=SHMEM_NAME, access=mmap.ACCESS_READ)
            try:
                content = shm[:].decode('utf-8').strip('\x00')
                if content:
                    return json.loads(content)
            finally:
                try: shm.close()
                except: pass
        except:
            pass
        return None

# Глобальный помощник
async def get_elevation_manager() -> ElevationManager:
    return await ElevationManager.get_instance()
