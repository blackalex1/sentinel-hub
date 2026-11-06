import ctypes
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL, CoInitialize
from ctypes import cast, POINTER

class VolumeManager:
    def __init__(self):
        self._volume = None
        self._initialized = False
        self.init_audio()

    def init_audio(self):
        try:
            CoInitialize()
            enumerator = AudioUtilities.GetDeviceEnumerator()
            device = enumerator.GetDefaultAudioEndpoint(0, 1) # Render, Console
            if device:
                interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self._volume = cast(interface, POINTER(IAudioEndpointVolume))
                self._initialized = True
        except Exception:
            self._initialized = False

    def get_volume(self):
        if not self._initialized: self.init_audio()
        if self._volume:
            try:
                return int(round(self._volume.GetMasterVolumeLevelScalar() * 100))
            except Exception:
                self._initialized = False
        return 0

    def is_muted(self):
        if not self._initialized: self.init_audio()
        if self._volume:
            try:
                return self._volume.GetMute() == 1
            except Exception:
                self._initialized = False
        return False

    def set_volume(self, level):
        if not self._initialized: self.init_audio()
        if self._volume:
            try:
                self._volume.SetMasterVolumeLevelScalar(level / 100.0, None)
                return True
            except Exception:
                self._initialized = False
        return False

    def set_mute(self, mute):
        if not self._initialized: self.init_audio()
        if self._volume:
            try:
                self._volume.SetMute(1 if mute else 0, None)
                return True
            except Exception:
                self._initialized = False
        return False

def press_media_key(vk_code):
    """Эмуляция нажатия медиа-клавиш Windows"""
    ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)
