import sys
import subprocess
import winreg
import os

def set_registry_value(hkey, subkey, value_name, value_data, sam=0):
    try:
        # Create or open key
        key = winreg.CreateKeyEx(hkey, subkey, 0, winreg.KEY_WRITE | sam)
        winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, value_data)
        winreg.CloseKey(key)
        print(f"Successfully set {subkey}\\{value_name} to {value_data}")
    except Exception as e:
        print(f"Failed to set {subkey}\\{value_name}: {e}")

def main():
    if len(sys.argv) < 2:
        print("Usage: register_camera.py <path_to_dll>")
        sys.exit(1)
        
    dll_path = os.path.abspath(sys.argv[1])
    if not os.path.exists(dll_path):
        print(f"DLL path not found: {dll_path}")
        sys.exit(1)
        
    # 1. Run regsvr32 to register the DirectShow filter
    print(f"Registering DirectShow filter DLL: {dll_path}")
    try:
        subprocess.run(["regsvr32", "/s", dll_path], check=True)
        print("regsvr32 completed successfully.")
    except Exception as e:
        print(f"regsvr32 failed: {e}")
        sys.exit(1)
        
    # 2. Modify registry friendly names so it displays as "MonitHome Camera"
    clsid = "{A7D691A0-5867-434E-B68C-A630560F4599}"
    category = "{860DB310-5D01-11d0-BD3B-00A0C911CE86}"
    camera_name = "MonitHome Camera"
    
    # Write to both 64-bit and 32-bit registry views to ensure full system compatibility
    for sam in [winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY]:
        # Update CLSID friendly name
        set_registry_value(winreg.HKEY_LOCAL_MACHINE, f"SOFTWARE\\Classes\\CLSID\\{clsid}", "", camera_name, sam)
        # Update DirectShow Category Instance friendly name
        set_registry_value(winreg.HKEY_LOCAL_MACHINE, f"SOFTWARE\\Classes\\CLSID\\{category}\\Instance\\{clsid}", "FriendlyName", camera_name, sam)
        
    print("Registration and renaming completed successfully!")

if __name__ == "__main__":
    main()
