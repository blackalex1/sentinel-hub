import ctypes
import ctypes.wintypes
import struct

# Настройка типов для WinAPI (критично для 64-бит систем)
kernel32 = ctypes.windll.kernel32
kernel32.OpenFileMappingW.restype = ctypes.wintypes.HANDLE
kernel32.OpenFileMappingW.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]

kernel32.MapViewOfFile.restype = ctypes.c_void_p
kernel32.MapViewOfFile.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.c_size_t]

kernel32.UnmapViewOfFile.restype = ctypes.wintypes.BOOL
kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]

kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]

def get_afterburner_stats():
    """
    Универсальный читатель Shared Memory MSI Afterburner.
    Автоматически адаптируется под разные версии и размеры структур.
    """
    stats = {}
    
    # Открываем именованную память
    handle = kernel32.OpenFileMappingW(0x0004, False, "MAHMSharedMemory")
    if not handle:
        return None
    
    try:
        p_view = kernel32.MapViewOfFile(handle, 0x0004, 0, 0, 0)
        if not p_view:
            return None
            
        try:
            # Читаем расширенный заголовок (32 байта)
            header_data = ctypes.string_at(p_view, 32)
            sig, ver, h_size, ent_cnt, ent_size, m_time, num_gpu, gpu_info_size = struct.unpack('IIIIIIII', header_data)
            
            if sig != 0x4D41484D: # 'MAHM'
                return None

            # 1. Читаем данные сенсоров
            for i in range(ent_cnt):
                entry_addr = p_view + h_size + (i * ent_size)
                name = ctypes.string_at(entry_addr, 32).decode('ascii', 'ignore').strip('\x00')
                
                data_addr = entry_addr + ent_size - 24
                value = struct.unpack('f', ctypes.string_at(data_addr, 4))[0]
                
                if value > 3e38: continue

                name_lower = name.lower()
                if "gpu" in name_lower and "temperature" in name_lower:
                    stats['gpu_temp'] = value
                elif "gpu" in name_lower and ("usage" in name_lower or "load" in name_lower):
                    stats['gpu_load'] = value
                elif "cpu" in name_lower and "temperature" in name_lower:
                    # Если есть несколько ядер, берем максимальную или первую попавшуюся
                    if 'cpu_temp' not in stats or value > stats['cpu_temp']:
                        stats['cpu_temp'] = value
                elif "cpu" in name_lower and ("usage" in name_lower or "load" in name_lower):
                    if 'cpu_load' not in stats or value > stats['cpu_load']:
                        stats['cpu_load'] = value
                elif name == "RAM usage":
                    stats['ram_used'] = value / 1024 if value > 1000 else value
                elif name == "Framerate":
                    stats['fps'] = value

            # 2. Читаем название GPU (перебор всех карт)
            if num_gpu > 0:
                for g in range(num_gpu):
                    gpu_info_addr = p_view + h_size + (ent_cnt * ent_size) + (g * gpu_info_size)
                    # Friendly name находится по смещению 256 внутри GPU_INFO
                    gpu_name = ctypes.string_at(gpu_info_addr + 256, 256).decode('ascii', 'ignore').strip('\x00')
                    if gpu_name:
                        stats['gpu_name'] = gpu_name
                        break # Берем первую найденную с именем

            return stats if stats else None
                    
        finally:
            kernel32.UnmapViewOfFile(p_view)
    finally:
        kernel32.CloseHandle(handle)

if __name__ == "__main__":
    # Тестовый запуск
    print(get_afterburner_stats())
