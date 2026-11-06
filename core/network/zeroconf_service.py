import logging
from zeroconf import IPVersion
from zeroconf.asyncio import AsyncZeroconf
import asyncio

logger = logging.getLogger("ZeroconfService")

class ZeroconfService:
    """
    Единый сервис для управления mDNS (Zeroconf).
    Предотвращает создание множества экземпляров Zeroconf в приложении.
    """
    _instance = None
    _lock = asyncio.Lock()

    def __init__(self):
        self.aio_zeroconf = None
        self._initialized = False

    @classmethod
    async def get_instance(cls):
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    async def initialize(self, interfaces=None):
        """Инициализация синглтона Zeroconf"""
        if self._initialized:
            return self.aio_zeroconf

        logger.info(f"Initializing unified Zeroconf service. Interfaces: {interfaces}")
        if interfaces is not None:
            self.aio_zeroconf = AsyncZeroconf(ip_version=IPVersion.V4Only, interfaces=interfaces)
        else:
            self.aio_zeroconf = AsyncZeroconf(ip_version=IPVersion.V4Only)
        self._initialized = True
        return self.aio_zeroconf

    async def get_zeroconf(self) -> AsyncZeroconf:
        if not self._initialized:
            await self.initialize()
        return self.aio_zeroconf

    async def shutdown(self):
        if self._initialized and self.aio_zeroconf:
            logger.info("Shutting down unified Zeroconf service...")
            await self.aio_zeroconf.async_close()
            self._initialized = False
            self.aio_zeroconf = None

# Global helper for easier access
async def get_zeroconf() -> AsyncZeroconf:
    service = await ZeroconfService.get_instance()
    return await service.get_zeroconf()
