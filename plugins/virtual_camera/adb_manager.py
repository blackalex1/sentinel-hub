import asyncio
import logging
import subprocess
import sys

class ADBManager:
    def __init__(self, log_func):
        self.log = log_func
        self.creationflags = 0x08000000 if sys.platform == "win32" else 0

    async def run_monitor_loop(self):
        # Check if adb command is available
        has_adb = True
        try:
            await asyncio.to_thread(
                lambda: subprocess.run(["adb", "--version"], capture_output=True, timeout=2.0, creationflags=self.creationflags)
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            has_adb = False
            self.log(
                "ADB is not installed or not in the system PATH. "
                "USB streaming will not be available unless configured.",
                level=logging.WARNING
            )

        if not has_adb:
            return

        adb_connected = False
        while True:
            try:
                # Check if any ADB devices are connected
                result = await asyncio.to_thread(
                    lambda: subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=2.0, creationflags=self.creationflags)
                )
                lines = result.stdout.strip().split("\n")
                devices = [line.split()[0] for line in lines[1:] if line.strip() and "device" in line]
                
                if devices:
                    if not adb_connected:
                        self.log(f"USB device detected ({devices[0]}) via ADB monitor. Setting up reverse port mapping (5000->5000)...")
                        adb_connected = True
                        
                        # Setup ADB reverse (Tablet -> PC)
                        await asyncio.to_thread(
                            lambda: subprocess.run(["adb", "reverse", "tcp:5000", "tcp:5000"], capture_output=True, timeout=2.0, creationflags=self.creationflags)
                        )
                        # Setup ADB forward (PC -> Tablet)
                        await asyncio.to_thread(
                            lambda: subprocess.run(["adb", "forward", "tcp:8554", "tcp:8554"], capture_output=True, timeout=2.0, creationflags=self.creationflags)
                        )
                else:
                    if adb_connected:
                        self.log("ADB device disconnected.")
                        adb_connected = False
            except Exception:
                pass
            await asyncio.sleep(5.0)

    def setup_usb_forwarding_if_available(self, rtsp_url: str) -> str:
        try:
            # Check if any ADB devices are connected
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=2.0, creationflags=self.creationflags)
            lines = result.stdout.strip().split("\n")
            devices = [line.split()[0] for line in lines[1:] if line.strip() and "device" in line]
            
            if devices:
                self.log(f"USB device detected ({devices[0]}). Setting up ADB port forwarding...")
                # Setup ADB forward (PC -> Tablet)
                subprocess.run(["adb", "forward", "tcp:8554", "tcp:8554"], capture_output=True, timeout=2.0, creationflags=self.creationflags)
                # Setup ADB reverse (Tablet -> PC)
                subprocess.run(["adb", "reverse", "tcp:5000", "tcp:5000"], capture_output=True, timeout=2.0, creationflags=self.creationflags)
                
                # Replace the tablet's Wi-Fi IP address with localhost (127.0.0.1) to force streaming over USB
                # e.g., "rtsp://192.168.1.116:8554/live" -> "rtsp://127.0.0.1:8554/live"
                if "://" in rtsp_url:
                    parts = rtsp_url.split("://")
                    path_parts = parts[1].split("/", 1)
                    host_port = path_parts[0]
                    path = path_parts[1] if len(path_parts) > 1 else ""
                    
                    port = "8554"
                    if ":" in host_port:
                        port = host_port.split(":")[1]
                        
                    rtsp_url = f"{parts[0]}://127.0.0.1:{port}/{path}"
                    self.log(f"USB connection active. Redirected stream to: {rtsp_url}")
            else:
                self.log("No USB devices detected via ADB. Using Wi-Fi connection.")
        except Exception as e:
            self.log(f"ADB check failed: {e}. Defaulting to Wi-Fi connection.")
        return rtsp_url
