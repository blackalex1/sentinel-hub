import logging
import socket
import asyncio
from zeroconf import ServiceInfo
from core.network.zeroconf_service import ZeroconfService

logger = logging.getLogger("Discovery")

class DiscoveryManager:
    def __init__(self, port: int = 5000):
        self.port = port
        self.service_info = None

    def get_local_ip(self):
        try:
            # Сначала пробуем стандартный способ через 8.8.8.8
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            
            # Если IP похож на Docker/VPN (172.x), попробуем найти альтернативу 192.168.x
            if ip.startswith("172."):
                import psutil
                addrs = psutil.net_if_addrs()
                for interface_name, interface_addresses in addrs.items():
                    for address in interface_addresses:
                        if address.family == socket.AF_INET:
                            if address.address.startswith("192.168.") or address.address.startswith("10."):
                                return address.address
            return ip
        except Exception:
            # Если интернета нет, ищем первый подходящий локальный IP среди интерфейсов
            try:
                import psutil
                addrs = psutil.net_if_addrs()
                for interface_name, interface_addresses in addrs.items():
                    for address in interface_addresses:
                        if address.family == socket.AF_INET:
                            addr = address.address
                            if not addr.startswith("127."):
                                if addr.startswith("192.168.") or addr.startswith("10.") or addr.startswith("172."):
                                    return addr
            except Exception:
                pass
            return "127.0.0.1"

    async def start(self):
        local_ip = await asyncio.to_thread(self.get_local_ip)
        hostname = socket.gethostname()
        
        from core.config import config_manager
        desc = {
            'version': '2.0.0',
            'server_uuid': config_manager.config.server_uuid,
            'hostname': config_manager.config.hostname
        }
        
        self.service_info = ServiceInfo(
            "_monithome._tcp.local.",
            f"MonitHome-{hostname}._monithome._tcp.local.",
            addresses=[socket.inet_aton(local_ip)],
            port=self.port,
            properties=desc,
            server=f"{hostname}.local.",
        )
        
        zc_service = await ZeroconfService.get_instance()
        aio_zeroconf = await zc_service.get_zeroconf()
        await aio_zeroconf.zeroconf.async_register_service(self.service_info)
        logger.info(f"mDNS Service registered: {local_ip}:{self.port} (MonitHome-{hostname})")

    async def stop(self):
        if self.service_info:
            zc_service = await ZeroconfService.get_instance()
            aio_zeroconf = await zc_service.get_zeroconf()
            await aio_zeroconf.zeroconf.async_unregister_service(self.service_info)
            logger.info("mDNS Service unregistered.")
