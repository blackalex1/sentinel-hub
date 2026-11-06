import subprocess
import os
import sys
import shutil

def build_single_exe():
    # 1. Настройки путей
    # Мы находимся в /bin, корень проекта на уровень выше
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(bin_dir)
    pc_v2_dir = os.path.join(project_root, "pc_v2")
    
    entry_script = os.path.join(pc_v2_dir, "pc_gui_app.py")
    output_name = "MonitHome"
    
    print(f"--- Preparing build environment ---")
    print(f"Project root: {project_root}")
    
    # Очистка временных файлов (но не трогаем саму папку bin, кроме старого EXE)
    build_tmp = os.path.join(project_root, "build_tmp")
    spec_file = os.path.join(project_root, f"{output_name}.spec")
    
    for path in [build_tmp, spec_file]:
        if os.path.exists(path):
            if os.path.isdir(path): shutil.rmtree(path)
            else: os.remove(path)

    # 2. Сборка (режим --onefile)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--console",
        "--onefile",
        f"--name={output_name}",
        f"--distpath={bin_dir}",     # Собираем прямо сюда, в /bin
        f"--workpath={build_tmp}",
        "--clean",
        # Пути к данным должны быть относительно папки запуска или абсолютными
        f"--add-data={os.path.join(pc_v2_dir, 'web')};web",
        f"--add-data={os.path.join(pc_v2_dir, 'plugins')};plugins",
        f"--icon={os.path.join(project_root, 'icons', 'pc_icon.ico')}",
        entry_script
    ]

    print(f"--- Running PyInstaller ---")
    try:
        subprocess.run(cmd, check=True)
        
        # Очистка
        if os.path.exists(build_tmp): shutil.rmtree(build_tmp)
        if os.path.exists(spec_file): os.remove(spec_file)

        print("\n" + "="*50)
        print(f"BUILD SUCCESSFUL!")
        print(f"Your single executable is here: {os.path.join(bin_dir, output_name + '.exe')}")
        print("="*50)
            
    except Exception as e:
        print(f"\nBUILD FAILED: {e}")

if __name__ == "__main__":
    build_single_exe()
