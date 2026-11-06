import subprocess
import os
import sys
import shutil

def build_single_exe():
    # 1. Настройки путей
    # Скрипт лежит в /bin, значит корень проекта на уровень выше
    bin_folder = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(bin_folder)
    pc_v2_path = os.path.join(project_root, "pc_v2")
    
    entry_script = os.path.join(pc_v2_path, "pc_gui_app.py")
    output_name = "MonitHome"
    
    print(f"--- Preparing build environment (Root: {project_root}) ---")
    
    # Очистка старых временных файлов в папке bin
    work_path = os.path.join(bin_folder, "build_tmp")
    spec_path = os.path.join(bin_folder, f"{output_name}.spec")
    
    for path in [work_path, spec_path]:
        if os.path.exists(path):
            if os.path.isdir(path): shutil.rmtree(path)
            else: os.remove(path)

    # Check if --clean is requested in command-line arguments
    use_clean = "--clean" in sys.argv

    # 2. Сборка
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        f"--name={output_name}",
        f"--distpath={bin_folder}",   # EXE упадет прямо в папку bin
        f"--workpath={work_path}",
        f"--specpath={bin_folder}",
        "--noupx",
        # Исключаем тяжелые неиспользуемые модули для ускорения анализа и уменьшения размера EXE
        "--exclude-module=numpy",
        "--exclude-module=pandas",
        "--exclude-module=matplotlib",
        "--exclude-module=scipy",
        "--exclude-module=tkinter",
        "--exclude-module=IPython",
        # Указываем полные пути к папкам данных в pc_v2
        f"--add-data={os.path.join(pc_v2_path, 'web')};web",
        f"--add-data={os.path.join(pc_v2_path, 'plugins')};plugins",
        "--hidden-import=wmi",
        "--hidden-import=win32api",
        "--hidden-import=win32com",
        "--hidden-import=pycaw",
        "--hidden-import=pycaw.pycaw",
        "--hidden-import=comtypes",
        "--hidden-import=comtypes.stream",
        "--hidden-import=pythonnet",
        "--hidden-import=clr",
        f"--icon={os.path.join(project_root, 'icons', 'pc_icon.ico')}",
        entry_script
    ]

    if use_clean:
        cmd.append("--clean")

    print(f"--- Running PyInstaller ---")
    try:
        subprocess.run(cmd, check=True)
        
        # Очистка
        if os.path.exists(work_path): shutil.rmtree(work_path)
        if os.path.exists(spec_path): os.remove(spec_path)

        print("\n" + "="*50)
        print(f"BUILD SUCCESSFUL! Result: {os.path.join(bin_folder, output_name + '.exe')}")
        print("="*50)
            
    except Exception as e:
        print(f"\nBUILD FAILED: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build_single_exe()
