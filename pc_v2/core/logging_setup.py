import logging
import asyncio
import time

class SocketIOHandler(logging.Handler):
    _last_msg = None

    def __init__(self, sio):
        super().__init__()
        self.sio = sio

    def emit(self, record):
        try:
            t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
            msg = f"{t} [{record.levelname}] {record.name}: {record.getMessage()}"
            
            if msg == SocketIOHandler._last_msg:
                return
            
            SocketIOHandler._last_msg = msg
            
            loop = asyncio.get_running_loop()
            loop.create_task(self.sio.emit("server_log", {"message": msg}, room="authorized"))
        except:
            pass

def setup_logging(sio):
    if not hasattr(logging, "_monithome_handler_initialized"):
        socket_log_handler = SocketIOHandler(sio)
        socket_log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        socket_log_handler.name = "MonitHomeSocketHandler"
        
        root_logger = logging.getLogger()
        root_logger.handlers = [h for h in root_logger.handlers if getattr(h, "name", "") != "MonitHomeSocketHandler" and h.__class__.__name__ != "SocketIOHandler"]
        root_logger.addHandler(socket_log_handler)
        logging._monithome_handler_initialized = True
