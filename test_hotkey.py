import ctypes
import time
import sys

def test_hotkey():
    print("[*] Начинаем тест симуляции клавиатуры...")
    print("[*] Через 3 секунды мы симулируем нажатие Win+D (свернуть все окна).")
    print("[*] Пожалуйста, следите за вашим рабочим столом!")
    
    for i in range(3, 0, -1):
        print(f"[{i}]...")
        time.sleep(1)
        
    try:
        # Win key = 0x5B (91), D key = 68
        vk_win = 0x5B
        vk_d = ord('D')
        
        print("[+] Нажимаем Win...")
        ctypes.windll.user32.keybd_event(vk_win, 0, 0, 0)
        time.sleep(0.05)
        
        print("[+] Нажимаем D...")
        ctypes.windll.user32.keybd_event(vk_d, 0, 0, 0)
        time.sleep(0.05)
        
        print("[+] Отпускаем D...")
        ctypes.windll.user32.keybd_event(vk_d, 0, 2, 0)
        time.sleep(0.05)
        
        print("[+] Отпускаем Win...")
        ctypes.windll.user32.keybd_event(vk_win, 0, 2, 0)
        
        print("[+] Симуляция завершена успешно!")
    except Exception as e:
        print(f"[-] Ошибка во время теста: {e}")

if __name__ == "__main__":
    test_hotkey()
