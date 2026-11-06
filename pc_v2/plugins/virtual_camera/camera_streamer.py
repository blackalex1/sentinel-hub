import asyncio
import logging
import os
from .rtsp_reader import RTSPStreamReader

class CameraStreamer:
    def __init__(self, plugin, log_func):
        self.plugin = plugin
        self.log = log_func
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))

    async def run_stream_loop(self, rtsp_url: str, width: int = 640, height: int = 480):
        self.plugin._is_streaming = True
        reader = None
        
        try:
            try:
                import cv2
                import pyvirtualcam
            except ImportError as e:
                self.log(
                    f"Missing Python dependencies (opencv-python, pyvirtualcam): {e}. "
                    f"Please run 'pip install -r requirements.txt' in the pc_v2 directory.",
                    level=logging.ERROR
                )
                return

            self.log(f"Using camera stream resolution: {width}x{height}")

            # Start the FFmpeg RTSP reader with retries to handle initialization latency
            max_attempts = 5
            reader = None
            for attempt in range(1, max_attempts + 1):
                if not self.plugin._is_streaming:
                    return
                self.log(f"Connecting to RTSP stream (Attempt {attempt}/{max_attempts})...")
                
                reader = RTSPStreamReader(rtsp_url, width, height, self.log)
                reader.start()
                
                # Wait for the first frame to arrive (timeout after 5 seconds per attempt)
                self.log("Waiting for incoming RTSP frames...")
                success = False
                for _ in range(50):
                    if not self.plugin._is_streaming:
                        reader.stop()
                        return
                    if not reader.running:
                        self.log("RTSP Reader process terminated early. Aborting wait for this attempt.", level=logging.WARNING)
                        break
                    ret, frame, frame_id = reader.read()
                    if ret and frame is not None:
                        success = True
                        break
                    await asyncio.sleep(0.1)
                
                if success:
                    break
                else:
                    self.log(f"Attempt {attempt} failed to receive frames (stream warm-up or connection pending).", level=logging.WARNING)
                    reader.stop()
                    if attempt < max_attempts:
                        await asyncio.sleep(1.0)
            else:
                self.log("Failed to receive initial frames from RTSP stream after all attempts.", level=logging.ERROR)
                try:
                    ffmpeg_log_path = os.path.join(self.plugin_dir, "ffmpeg_error.log")
                    if os.path.exists(ffmpeg_log_path):
                        with open(ffmpeg_log_path, "r", encoding="utf-8", errors="ignore") as f:
                            errors = f.read().strip()
                            if errors:
                                self.log(f"FFmpeg stderr log:\n{errors}", level=logging.ERROR)
                except Exception as log_err:
                    self.log(f"Failed to read FFmpeg log: {log_err}")
                return

            self.log("Initial frames received. Broadcasting to virtual webcam...")
            
            # Stream frames to the virtual camera
            last_frame_id = -1
            import time
            self.plugin.last_client_activity = time.time()
            
            while self.plugin._is_streaming:
                if not reader.running:
                    self.log("RTSP Reader stopped unexpectedly or EOF reached. Terminating stream loop.")
                    break
                    
                # Check if the client application (OBS) wants frames.
                # h_want is signaled by the client filter when it desires new frames.
                h_want = getattr(self.plugin, "h_want", None)
                if h_want:
                    try:
                        import win32event
                        res = win32event.WaitForSingleObject(h_want, 0)
                        if res == win32event.WAIT_OBJECT_0:
                            # Signaled means client is actively requesting frames!
                            self.plugin.last_client_activity = time.time()
                    except Exception as e:
                        self.log(f"Error checking h_want state: {e}", level=logging.DEBUG)
                    
                ret, frame, frame_id = reader.read()
                if not ret or frame is None or frame_id == last_frame_id:
                    # No new frame yet, yield to event loop briefly
                    await asyncio.sleep(0.01)
                    continue

                last_frame_id = frame_id

                # Resize to 1920x1080 if the incoming frame is different
                # This guarantees compatibility with client applications (OBS) requesting 1080p
                f_height, f_width = frame.shape[:2]
                if f_width != 1920 or f_height != 1080:
                    frame = cv2.resize(frame, (1920, 1080), interpolation=cv2.INTER_LINEAR)

                # Convert BGR (FFmpeg raw) to RGB (pyvirtualcam)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Initialize virtual camera device dynamically if not already initialized
                if self.plugin.cam is None:
                    self.log("Initializing pyvirtualcam device with resolution: 1920x1080")
                    try:
                        self.plugin.cam = pyvirtualcam.Camera(
                            width=1920,
                            height=1080,
                            fps=30,
                            backend="unitycapture"
                        )
                        self.log(f"Virtual camera active: {self.plugin.cam.device}")
                    except Exception as e:
                        self.log(f"Failed to start pyvirtualcam: {e}", level=logging.ERROR)
                        break

                # Write the absolute latest frame to the virtual device
                self.plugin.cam.send(frame_rgb)

        except asyncio.CancelledError:
            self.log("Camera streaming task cancelled.")
        except Exception as e:
            self.log(f"Error in camera streaming loop: {e}", level=logging.ERROR)
        finally:
            if reader:
                reader.stop()
            self.plugin._is_streaming = False
            self.log("Camera stream released.")
