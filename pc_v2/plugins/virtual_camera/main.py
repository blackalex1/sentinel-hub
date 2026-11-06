import os
# Force low latency FFmpeg capture options over TCP with low_delay at the absolute top of the file
# This ensures it is in the environment BEFORE cv2 is ever imported in this process
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|analyzeduration;100000|probesize;100000"

import asyncio
import logging

from plugin_engine.base_plugin import BasePlugin
from .camera_utils import is_camera_registered, register_camera, download_dll
from .adb_manager import ADBManager
from .camera_monitor import CameraActivityMonitor
from .camera_streamer import CameraStreamer


class Plugin(BasePlugin):
    def __init__(self, plugin_id: str):
        super().__init__(plugin_id)
        self._stream_task = None
        self._adb_task = None
        self._monitor_task = None
        self._is_streaming = False
        self._pause_send = False
        self.cam = None
        self.auto_start_active = False
        self.auto_start_initiating = False
        
        # Paths
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.bin_dir = os.path.join(self.plugin_dir, "bin")
        self.dll_path = os.path.join(self.bin_dir, "UnityCaptureFilter64.dll")
        self.register_script = os.path.join(self.plugin_dir, "register_camera.py")

        # Helpers
        self.adb_manager = ADBManager(self.log)
        self.activity_monitor = CameraActivityMonitor(self, self.log)
        self.streamer = CameraStreamer(self, self.log)

    async def on_start(self):
        self.log("virtual_camera starting...")
        
        # 1. Ensure bin directory exists
        os.makedirs(self.bin_dir, exist_ok=True)
        
        # 2. Check and download DLL if missing
        if not os.path.exists(self.dll_path):
            self.log("UnityCaptureFilter64.dll not found, downloading from GitHub...")
            try:
                await asyncio.to_thread(download_dll, self.dll_path)
                self.log("DLL downloaded successfully.")
            except Exception as e:
                self.log(f"Failed to download DLL: {e}", level=logging.ERROR)
                
        # 3. Check and register DLL if not registered
        if os.path.exists(self.dll_path):
            if not is_camera_registered():
                self.log("MonitHome Camera is not registered. Requesting UAC elevation...")
                try:
                    await asyncio.to_thread(register_camera, self.register_script, self.dll_path)
                    self.log("UAC elevation request sent.")
                except Exception as e:
                    self.log(f"Failed to execute registration script: {e}", level=logging.ERROR)
            else:
                self.log("MonitHome Camera is already registered.")

        # 4. Start periodic ADB connection check and port mapping
        self._adb_task = self.create_task(self.adb_manager.run_monitor_loop())
        
        # 5. Start camera event usage monitor loop
        self._monitor_task = self.create_task(self.activity_monitor.run_monitor_loop())

    async def on_stop(self):
        if self._adb_task:
            self._adb_task.cancel()
            try:
                await self._adb_task
            except asyncio.CancelledError:
                pass
            self._adb_task = None
            
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
            
        await self._stop_stream()
        
        if self.cam:
            try:
                self.cam.close()
            except:
                pass
            self.cam = None
            
        self.log("virtual_camera stopped.")

    async def handle_command(self, action: str, data: any):
        if action == "start_camera":
            rtsp_url = None
            use_usb = False
            width = 640
            height = 480
            if isinstance(data, dict):
                rtsp_url = data.get("rtsp_url")
                use_usb = data.get("use_usb", False)
                width = data.get("width", 640)
                height = data.get("height", 480)
            elif isinstance(data, str):
                rtsp_url = data
                
            if rtsp_url:
                if use_usb:
                    rtsp_url = self.adb_manager.setup_usb_forwarding_if_available(rtsp_url)
                else:
                    self.log("Streaming mode set to Wi-Fi. Bypassing USB routing.")
                await self._stop_stream()
                
                # If we didn't initiate this start automatically, mark auto_start_active as False
                if not getattr(self, "auto_start_initiating", False):
                    self.auto_start_active = False
                else:
                    self.auto_start_initiating = False
                    
                self._stream_task = self.create_task(self.streamer.run_stream_loop(rtsp_url, 1280, 720))
                self.log(f"Started camera stream reader task for {rtsp_url} (1280x720)")
        elif action == "stop_camera":
            await self._stop_stream()
            self.log("Stopped camera stream reader task.")

    async def _stop_stream(self):
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
            self._is_streaming = False
            
            # Send placeholder frame to reset the camera display to waiting mode
            try:
                if self.cam:
                    import cv2
                    import numpy as np
                    w, h = 1920, 1080
                    placeholder = np.zeros((h, w, 3), dtype=np.uint8)
                    cv2.putText(placeholder, "MonitHome Camera", (650, 480), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 165, 255), 3)
                    cv2.putText(placeholder, "Waiting for stream...", (780, 560), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)
                    placeholder_rgb = cv2.cvtColor(placeholder, cv2.COLOR_BGR2RGB)
                    self.cam.send(placeholder_rgb)
            except Exception as e:
                self.log(f"Failed to send reset placeholder: {e}")
