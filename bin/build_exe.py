import subprocess
import os
import sys
import shutil

def build_single_exe():
    bin_folder = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(bin_folder)
    
    entry_script = os.path.join(project_root, "pc_gui_app.py")
    output_name = "SentinelHub"
    
    print(f"--- Preparing build environment for Sentinel Hub (Root: {project_root}) ---")
    
    work_path = os.path.join(bin_folder, "build_tmp")
    spec_path = os.path.join(bin_folder, f"{output_name}.spec")
    
    for path in [work_path, spec_path]:
        if os.path.exists(path):
            if os.path.isdir(path): shutil.rmtree(path)
            else: os.remove(path)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        f"--name={output_name}",
        f"--distpath={bin_folder}",
        f"--workpath={work_path}",
        f"--specpath={bin_folder}",
        "--noupx",
        "--exclude-module=numpy",
        "--exclude-module=pandas",
        "--exclude-module=matplotlib",
        "--exclude-module=scipy",
        "--exclude-module=tkinter",
        "--exclude-module=IPython",
        f"--add-data={os.path.join(project_root, 'web')};web",
        f"--add-data={os.path.join(project_root, 'plugins')};plugins",
        f"--add-data={os.path.join(project_root, 'bin', 'MonitHomeHelper.exe')};bin",
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

    print(f"--- Running PyInstaller for Sentinel Hub ---")
    try:
        subprocess.run(cmd, check=True)
        if os.path.exists(work_path): shutil.rmtree(work_path)
        if os.path.exists(spec_path): os.remove(spec_path)
        print(f"\n[SUCCESS] Sentinel Hub built successfully -> {os.path.join(bin_folder, f'{output_name}.exe')}")
        # Создаем также копию под именем MonitHome.exe для обратной совместимости
        monithome_copy = os.path.join(bin_folder, "MonitHome.exe")
        shutil.copyfile(os.path.join(bin_folder, f'{output_name}.exe'), monithome_copy)
        print(f"[SUCCESS] Compatibility copy created -> {monithome_copy}")
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Build failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build_single_exe()
