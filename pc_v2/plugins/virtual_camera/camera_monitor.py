import asyncio
import logging
import time
from .camera_utils import is_camera_registered

class CameraActivityMonitor:
    def __init__(self, plugin, log_func):
        self.plugin = plugin
        self.log = log_func

    async def run_monitor_loop(self):
        import pyvirtualcam
        import win32event
        import win32con
        import cv2
        import numpy as np
        import win32api

        # Wait until DLL is registered
        while not is_camera_registered():
            await asyncio.sleep(1.0)
            
        self.log("MonitHome Camera DLL verified. Initializing pyvirtualcam device for monitoring...")
        
        width, height = 1920, 1080
        event_name = r"Local\UnityCapture_Want"
        mutex_name = r"Local\UnityCapture_Mutx"
        sent_name = r"Local\UnityCapture_Sent"
        data_name = r"Local\UnityCapture_Data"
        shmem_size = 32 + 3840 * 2160 * 4 * 2 # Max possible size for safety (approx 66MB)
        
        import ctypes
        from ctypes import wintypes
        
        h_mutex = None
        h_want = None
        h_sent = None
        h_mapping = None
        
        try:
            # Setup ctypes for win32 calls to ensure correct types on 64-bit Windows
            kernel32 = ctypes.windll.kernel32
            kernel32.CreateMutexA.argtypes = [ctypes.c_void_p, wintypes.BOOL, ctypes.c_char_p]
            kernel32.CreateMutexA.restype = wintypes.HANDLE
            kernel32.CreateEventA.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, ctypes.c_char_p]
            kernel32.CreateEventA.restype = wintypes.HANDLE
            kernel32.CreateFileMappingA.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_char_p]
            kernel32.CreateFileMappingA.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL

            # Pre-create all UnityCapture IPC objects so they exist before pyvirtualcam and OBS start.
            # This breaks the chicken-and-egg problem where pyvirtualcam cannot initialize/send
            # if OBS is not running, and OBS cannot initialize if pyvirtualcam has not created the events.
            h_mutex = kernel32.CreateMutexA(None, False, mutex_name.encode('ascii'))
            h_want = kernel32.CreateEventA(None, False, False, event_name.encode('ascii'))
            h_sent = kernel32.CreateEventA(None, False, False, sent_name.encode('ascii'))
            h_mapping = kernel32.CreateFileMappingA(-1, None, 0x04, 0, shmem_size, data_name.encode('ascii'))
            
            # Setup MapViewOfFile to initialize maxSize in shared memory
            kernel32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
            kernel32.MapViewOfFile.restype = ctypes.c_void_p
            kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
            kernel32.UnmapViewOfFile.restype = wintypes.BOOL
            
            p_buf = kernel32.MapViewOfFile(h_mapping, 0x02, 0, 0, shmem_size) # FILE_MAP_WRITE = 0x02
            if p_buf:
                max_size_val = 3840 * 2160 * 4 * 2 # 66355200
                ctypes.memmove(p_buf, ctypes.byref(ctypes.c_uint32(max_size_val)), 4)
                kernel32.UnmapViewOfFile(p_buf)
            
            # Store pre-created Win32 handles in the plugin class for accessibility in other tasks
            self.plugin.h_mutex = h_mutex
            self.plugin.h_want = h_want
            self.plugin.h_sent = h_sent
            self.plugin.h_mapping = h_mapping
            
            self.log("UnityCapture IPC objects (mutex, events, file mapping) pre-created successfully.")
            
            # Create the pyvirtualcam device. This will open the already pre-created events and file mapping.
            self.plugin.cam = pyvirtualcam.Camera(width=width, height=height, fps=30, backend="unitycapture")
            self.log("Virtual camera device initialized for auto-start monitoring.")
            
            # Create a simple placeholder frame
            placeholder = np.zeros((height, width, 3), dtype=np.uint8)
            cv2.putText(placeholder, "MonitHome Camera", (650, 480), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 165, 255), 3)
            cv2.putText(placeholder, "Waiting for stream...", (780, 560), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)
            placeholder_rgb = cv2.cvtColor(placeholder, cv2.COLOR_BGR2RGB)
            
            # Send the first placeholder frame to write the width/height (1920x1080) to the shared memory.
            # This is critical so OBS sees the camera as active and starts signaling.
            self.plugin.cam.send(placeholder_rgb)
            
            while True:
                # State machine
                is_streaming = (self.plugin._stream_task is not None)
                
                # Check if the event is signaled (DirectShow filter is requesting frames)
                is_active = False
                try:
                    result = win32event.WaitForSingleObject(h_want, 0)
                    if result == win32event.WAIT_OBJECT_0:
                        is_active = True
                except Exception as e:
                    self.log(f"Error checking event state: {e}", level=logging.ERROR)
                
                if is_active and not is_streaming:
                    # OBS opened the camera! Tell the tablet to start streaming
                    self.log("Auto-start: Client application opened the virtual camera. Requesting stream from tablet...")
                    self.plugin.auto_start_initiating = True
                    self.plugin.auto_start_active = True
                    self.plugin.last_client_activity = time.time()
                    # Send start command to the tablet
                    await self.plugin.emit_event("start_camera", {})
                    
                elif is_streaming:
                    # Inactivity timeout based directly on last_client_activity
                    last_activity = getattr(self.plugin, "last_client_activity", 0)
                    if last_activity > 0 and (time.time() - last_activity > 10.0):
                        self.log("Inactivity timeout: No client application is using the virtual camera. Stopping stream...")
                        self.plugin.auto_start_active = False
                        # Send stop command to the tablet
                        await self.plugin.emit_event("stop_camera", {})
                        
                        # Give the tablet 500ms to shut down the RTSP server gracefully before we kill FFmpeg
                        await asyncio.sleep(0.5)
                        
                        # Stop our own reader and release stream task
                        await self.plugin._stop_stream()
                        
                # Sleep and check again
                await asyncio.sleep(2.0)
                
        except asyncio.CancelledError:
            self.log("Camera monitor task cancelled.")
        except Exception as e:
            self.log(f"Error in camera monitor loop: {e}", level=logging.ERROR)
        finally:
            self.log("Camera monitor loop exiting. Cleaning up IPC handles...")
            # Close pyvirtualcam camera if it is still open
            if self.plugin.cam:
                try:
                    self.plugin.cam.close()
                except:
                    pass
                self.plugin.cam = None
                
            # Close pre-created Win32 handles
            kernel32 = ctypes.windll.kernel32
            for h in [h_mutex, h_want, h_sent, h_mapping]:
                if h:
                    try:
                        kernel32.CloseHandle(h)
                    except:
                        pass
                        
            # Reset plugin handles to None
            self.plugin.h_mutex = None
            self.plugin.h_want = None
            self.plugin.h_sent = None
            self.plugin.h_mapping = None
