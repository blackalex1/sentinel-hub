import os
import subprocess
import numpy as np
import time

class RTSPStreamReader:
    """
    Dedicated background reader thread that constantly drains the FFmpeg RTSP pipe.
    Uses raw bytes to bypass OpenCV's internal buffering on Windows.
    """
    def __init__(self, rtsp_url, width, height, log_func):
        self.rtsp_url = rtsp_url
        self.width = width
        self.height = height
        self.frame_size = width * height * 3
        self.log = log_func
        self.latest_frame = None
        self.frame_id = 0
        self.ret = False
        self.running = True
        self.thread = None
        self.process = None
        self.ffmpeg_log = None

    def start(self):
        import threading
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def _read_loop(self):
        ffmpeg_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg_error.log")
        
        cmd = [
            "ffmpeg",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-rtsp_transport", "tcp",
            "-probesize", "2048",
            "-analyzeduration", "1000",
            "-an",
            "-i", self.rtsp_url,
            "-vf", f"scale={self.width}:{self.height}",
            "-r", "30",
            "-threads", "1",
            "-f", "image2pipe",
            "-pix_fmt", "bgr24",
            "-vcodec", "rawvideo",
            "-"
        ]
        
        self.log(f"RTSP Reader starting FFmpeg subprocess for {self.rtsp_url}...")
        try:
            self.ffmpeg_log = open(ffmpeg_log_path, "w", encoding="utf-8")
            flags = 0x08000000 if os.name == 'nt' else 0
            self.process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=self.ffmpeg_log, 
                bufsize=10**7,
                creationflags=flags
            )
        except Exception as e:
            self.log(f"Failed to start FFmpeg subprocess: {e}")
            if self.ffmpeg_log:
                self.ffmpeg_log.close()
            self.running = False
            return

        def read_exact(stream, n):
            data = bytearray()
            while len(data) < n and self.running:
                packet = stream.read(n - len(data))
                if not packet:
                    return None
                data.extend(packet)
            return bytes(data)

        self.log("RTSP Reader connected successfully. Streaming frames from FFmpeg pipe...")
        try:
            while self.running:
                raw_frame = read_exact(self.process.stdout, self.frame_size)
                if not raw_frame:
                    self.log("RTSP Reader: FFmpeg process stdout closed (EOF). Stopping reader...")
                    break
                if len(raw_frame) != self.frame_size:
                    if self.running:
                        time.sleep(0.01)
                    continue
                    
                frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((self.height, self.width, 3))
                self.latest_frame = frame
                self.frame_id += 1
                self.ret = True
        finally:
            self.running = False
            if self.ffmpeg_log:
                try:
                    self.ffmpeg_log.close()
                except:
                    pass

    def read(self):
        return self.ret, self.latest_frame, self.frame_id

    def stop(self):
        self.running = False
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=1.0)
            except:
                pass
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.ffmpeg_log:
            try:
                self.ffmpeg_log.close()
            except:
                pass
