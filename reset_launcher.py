import os
import sqlite3

def main():
    # Находим файл базы данных в корне проекта
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "database.db")
    
    if not os.path.exists(db_path):
        print(f"[-] Файл базы данных не найден по пути: {db_path}")
        print("    Убедитесь, что запускаете скрипт из корневой папки проекта.")
        return

    print(f"[+] Найден файл базы данных: {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Проверяем, существует ли запись плагина
        cursor.execute("SELECT plugin_id FROM plugin_settings WHERE plugin_id = ?", ("app_launcher",))
        row = cursor.fetchone()
        
        if row:
            # Удаляем старый оверрайд конфигурации
            cursor.execute("DELETE FROM plugin_settings WHERE plugin_id = ?", ("app_launcher",))
            conn.commit()
            print("[+] Успешно удален старый оверрайд конфигурации 'app_launcher' из базы данных!")
            print("[+] При следующем запуске MonitHome загрузятся новые крутые макросы по умолчанию!")
        else:
            print("[*] В базе данных нет оверрайдов для 'app_launcher'.")
            print("[+] Новые макросы по умолчанию уже должны быть активны!")
            
        conn.close()
    except Exception as e:
        print(f"[-] Произошла ошибка при очистке БД: {e}")

if __name__ == "__main__":
    main()
