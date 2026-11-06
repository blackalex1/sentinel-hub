import os
import urllib.request
import winreg
import ctypes
import sys

def is_camera_registered() -> bool:
    clsid = "{A7D691A0-5867-434E-B68C-A630560F4599}"
    category = "{860DB310-5D01-11d0-BD3B-00A0C911CE86}"
    
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            f"SOFTWARE\\Classes\\CLSID\\{category}\\Instance\\{clsid}",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        ) as key:
            name, _ = winreg.QueryValueEx(key, "FriendlyName")
            if name == "MonitHome Camera":
                return True
    except FileNotFoundError:
        pass

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            f"SOFTWARE\\Classes\\CLSID\\{category}\\Instance\\{clsid}",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_32KEY
        ) as key:
            name, _ = winreg.QueryValueEx(key, "FriendlyName")
            if name == "MonitHome Camera":
                return True
    except FileNotFoundError:
        pass

    return False

def register_camera(register_script: str, dll_path: str):
    ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        f'"{register_script}" "{dll_path}"',
        None,
        1
    )

def download_dll(dll_path: str):
    url = "https://raw.githubusercontent.com/schellingb/UnityCapture/master/Install/UnityCaptureFilter64.dll"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as response, open(dll_path, 'wb') as out_file:
        out_file.write(response.read())
