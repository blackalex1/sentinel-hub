import sys
import os
import winreg
import logging

logger = logging.getLogger("Autostart")

class AutostartManager:
    REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "MonitHome"

    @staticmethod
    def get_executable_path():
        if getattr(sys, 'frozen', False):
            # If running as EXE
            return sys.executable
        else:
            # If running as script
            # We need to find pc_gui_app.py or main.py. 
            # In this project, pc_gui_app.py seems to be the entry point for the GUI.
            script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pc_gui_app.py")
            return f'"{sys.executable}" "{script_path}"'

    @classmethod
    def set_autostart(cls, enabled: bool):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.REG_KEY, 0, winreg.KEY_SET_VALUE)
            if enabled:
                path = cls.get_executable_path()
                full_command = f"{path} --minimized"
                winreg.SetValueEx(key, cls.APP_NAME, 0, winreg.REG_SZ, full_command)
                logger.info(f"Autostart enabled: {full_command}")
            else:
                try:
                    winreg.DeleteValue(key, cls.APP_NAME)
                    logger.info("Autostart disabled")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
            return True
        except Exception as e:
            logger.error(f"Failed to set autostart: {e}")
            return False

    @classmethod
    def is_enabled(cls) -> bool:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.REG_KEY, 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, cls.APP_NAME)
                enabled = True
            except FileNotFoundError:
                enabled = False
            winreg.CloseKey(key)
            return enabled
        except Exception as e:
            logger.error(f"Failed to check autostart status: {e}")
            return False
