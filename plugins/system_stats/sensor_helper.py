import os
import sys
import json
import time
import ctypes
import mmap
import argparse

# Настройка логирования в файл
def setup_logging():
    try:
        # Пытаемся создать лог в папке с хелпером
        if hasattr(sys, '_MEIPASS'):
            log_dir = os.path.dirname(sys.executable)
        else:
            log_dir = os.path.dirname(os.path.abspath(__file__))
        
        log_path = os.path.join(log_dir, "helper_debug.log")
        return open(log_path, "a", encoding="utf-8", buffering=1)
    except:
        return None

log_file = setup_logging()
if log_file:
    sys.stdout = log_file
    sys.stderr = log_file

def log(msg):
    if log_file:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_file.write(f"[{timestamp}] {msg}\n")
        log_file.flush()

log(f"--- Helper starting (PID: {os.getpid()}) ---")

def init_clr_and_dll(dll_path):
    log(f"Loading DLL: {dll_path}")
    try:
        import clr
        if not os.path.exists(dll_path):
            log(f"CRITICAL: DLL not found at {dll_path}")
            return None
        clr.AddReference(dll_path)
        from LibreHardwareMonitor.Hardware import Computer
        c = Computer()
        c.IsCpuEnabled = True
        c.IsGpuEnabled = True
        c.IsMemoryEnabled = True
        c.IsMotherboardEnabled = True
        c.IsStorageEnabled = True
        c.Open()
        log("LHM Computer initialized successfully")
        return c
    except Exception as e:
        log(f"DLL Init Error: {e}")
        return None

def is_process_running(pid):
    if pid <= 0: return True
    # GetProcessVersion возвращает 0, если процесс не найден
    return ctypes.windll.kernel32.GetProcessVersion(pid) != 0

SHMEM_NAME = "Local\\MonitHomeSensors_V9"
SHMEM_SIZE = 16384
MUTEX_NAME = "Local\\MonitHomeSensorHelperMutex_V5"

class SensorHelper:
    def __init__(self, parent_pid=0):
        self.computer = None
        self.shmem = None
        self.parent_pid = parent_pid
        self.is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        log(f"Helper context: Admin={self.is_admin}, ParentPID={self.parent_pid}")

    def run(self, dll_path):
        self.computer = init_clr_and_dll(dll_path)
        try:
            log(f"Opening shared memory: {SHMEM_NAME}")
            self.shmem = mmap.mmap(-1, SHMEM_SIZE, tagname=SHMEM_NAME)
            log("Shared memory opened")
            
            while True:
                if self.parent_pid > 0 and not is_process_running(self.parent_pid):
                    log("Parent process died, exiting...")
                    break

                stats = {
                    "is_admin": self.is_admin,
                    "last_update": time.time(),
                    "pid": os.getpid(),
                    "sensors": {},
                    "gpu_temp": 0, "gpu_load": 0, "cpu_temp": 0, "has_gpu": False, "gpu_name": None
                }
                
                if self.computer:
                    try:
                        # Сбор данных
                        # 1. Выбираем приоритетную видеокарту (дискретную)
                        best_gpu_name = None
                        best_gpu_is_discrete = False
                        for hardware in self.computer.Hardware:
                            h_name = hardware.Name
                            h_type = str(hardware.HardwareType).lower()
                            if "gpu" in h_type:
                                is_discrete = ("arc" in h_name.lower()) or (not any(x in h_name.lower() for x in ["graphics", "integrated", "vega", "basic render", "intel(r) hd", "intel(r) uhd", "intel(r) iris"]))
                                if not best_gpu_name or (is_discrete and not best_gpu_is_discrete):
                                    best_gpu_name = h_name
                                    best_gpu_is_discrete = is_discrete

                        for hardware in self.computer.Hardware:
                            hardware.Update()
                            h_name = hardware.Name
                            h_type = str(hardware.HardwareType).lower()
                            
                            is_gpu = "gpu" in h_type
                            is_cpu = "cpu" in h_type
                            
                            if is_cpu and (not stats.get("cpu_name") or stats["cpu_name"] == "CPU"):
                                stats["cpu_name"] = h_name
                            
                            if is_gpu and h_name == best_gpu_name:
                                stats["has_gpu"] = True
                                stats["gpu_name"] = h_name
                            
                            h_sensors = {}
                            for sensor in hardware.Sensors:
                                if sensor.Value is not None:
                                    s_type = str(sensor.SensorType).lower()
                                    s_name = sensor.Name
                                    val = round(float(sensor.Value), 2)
                                    
                                    # КРИТИЧЕСКИЕ ДАТЧИКИ (всегда берем)
                                    if is_gpu and h_name == best_gpu_name:
                                        if "core" in s_name.lower() or "package" in s_name.lower():
                                            if "temperature" in s_type: stats["gpu_temp"] = val
                                            if "load" in s_type: stats["gpu_load"] = val
                                    
                                    if is_cpu:
                                        if any(x in s_name for x in ["Package", "Tctl", "Tdie", "Core Max"]):
                                            if "temperature" in s_type: stats["cpu_temp"] = val
                                    
                                    # Остальные датчики (фильтруем лишнее)
                                    if any(x in s_name for x in ["D3D", "PCIe", "Security", "Optical Flow", "JPEG Decode", "VR", "Copy"]):
                                        continue
                                    
                                    h_sensors[f"{s_name} ({s_type})"] = val
                                    
                            stats["sensors"][h_name] = h_sensors

                        # log(f"Detected: CPU={stats.get('cpu_name')}, GPU={stats.get('gpu_name')} (T:{stats['gpu_temp']}, L:{stats['gpu_load']})")

                    except Exception as e:
                        log(f"Update Loop Error: {e}")
                        stats["error"] = str(e)
                
                # --- Запись статистики ---
                try:
                    json_str = json.dumps(stats)
                    data = json_str.encode('utf-8')
                    
                    if len(data) > SHMEM_SIZE - 1:
                        log(f"WARNING: Data too large ({len(data)} bytes), pruning sensors...")
                        stats["sensors"] = {"pruned": "too_large"}
                        data = json.dumps(stats).encode('utf-8')
                    
                    data = data.ljust(SHMEM_SIZE, b'\x00')
                    self.shmem.seek(0)
                    self.shmem.write(data)
                except Exception as e:
                    log(f"Write SHMEM Error: {e}")

                # --- Чтение и выполнение команд ---
                try:
                    cmd_shm = mmap.mmap(-1, 1024, tagname="Local\\MonitHomeCommands_V9", access=mmap.ACCESS_READ)
                    try:
                        cmd_data = cmd_shm[:].decode('utf-8').strip('\x00')
                        if cmd_data:
                            clear_shm = mmap.mmap(-1, 1024, tagname="Local\\MonitHomeCommands_V9", access=mmap.ACCESS_WRITE)
                            clear_shm.write(b'\x00' * 1024)
                            clear_shm.close()
                            
                            log(f"Received command: {cmd_data}")
                            cmd_obj = json.loads(cmd_data)
                            action = cmd_obj.get("action")
                            if action == "shell_exec":
                                command = cmd_obj.get("command")
                                if command:
                                    log(f"Executing privileged command: {command}")
                                    import subprocess
                                    subprocess.Popen(command, shell=True, creationflags=0x08000000)
                            elif action == "shutdown":
                                os.system("shutdown /s /t 5 /f")
                            elif action == "restart":
                                os.system("shutdown /r /t 5 /f")
                    finally:
                        try: cmd_shm.close()
                        except: pass
                except:
                    pass

                # В конце цикла вызываем gc.collect() для очистки pythonnet оберток
                import gc
                gc.collect()

                time.sleep(1)
        except Exception as e:
            log(f"Fatal Error: {e}")
        finally:
            log("Helper shutting down...")
            if self.computer: self.computer.Close()
            if self.shmem: self.shmem.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int, default=0)
    args = parser.parse_args()
    
    # Mutex
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == 183:
        log("Mutex already held by another process, exiting.")
        sys.exit(0)

    if hasattr(sys, '_MEIPASS'):
        dll_path = os.path.join(sys._MEIPASS, "bin", "LibreHardwareMonitorLib.dll")
    else:
        script_path = os.path.abspath(__file__)
        dll_path = os.path.join(os.path.dirname(script_path), "bin", "LibreHardwareMonitorLib.dll")
    
    helper = SensorHelper(parent_pid=args.parent_pid)
    helper.run(dll_path)
