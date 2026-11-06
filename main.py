import asyncio
import logging
import sys

# Monkey-patch for Windows-specific asyncio ProactorEventLoop connection lost log noise
if sys.platform == "win32":
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport
        _orig_call_connection_lost = _ProactorBasePipeTransport._call_connection_lost

        def _patched_call_connection_lost(self, exc):
            try:
                _orig_call_connection_lost(self, exc)
            except (OSError, AttributeError):
                pass

        _ProactorBasePipeTransport._call_connection_lost = _patched_call_connection_lost
    except ImportError:
        pass

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from contextlib import asynccontextmanager

from network.socket_server import sio, socket_manager
from network.discovery import DiscoveryManager
from plugin_engine.manager import plugin_manager
from core.config import config_manager
from core.logging_setup import setup_logging
import socketio

# Импорт роутеров
from api.plugins import router as plugins_router
from api.config import router as config_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MonitHome PC...")
    await socket_manager.initialize()
    await plugin_manager.initialize()
    
    from core.i18n import I18nManager
    I18nManager.get_instance().set_language(config_manager.config.language)
    
    from core.elevation import get_elevation_manager
    em = await get_elevation_manager()
    await em.start()
    
    discovery = DiscoveryManager(port=5000)
    asyncio.create_task(discovery.start())
    app.state.discovery = discovery
    
    logger.info("Server is up and running.")
    yield
    
    logger.info("Shutting down...")
    if hasattr(app.state, 'discovery'):
        await app.state.discovery.stop()
    
    from core.network.zeroconf_service import ZeroconfService
    zc_service = await ZeroconfService.get_instance()
    await zc_service.shutdown()
    
    from core.elevation import get_elevation_manager
    em = await get_elevation_manager()
    await em.stop()
    
    await plugin_manager.shutdown()
    config_manager.db.close()

app = FastAPI(lifespan=lifespan)

# Настройка логирования через Socket.IO
setup_logging(sio)

# Подключаем API роутеры
app.include_router(plugins_router)
app.include_router(config_router)

# Раздача статики
from core.config import BUNDLE_DIR
web_dir = os.path.join(BUNDLE_DIR, "web")
if not os.path.exists(web_dir): os.makedirs(web_dir)
app.mount("/static", StaticFiles(directory=web_dir), name="static")

@app.get("/")
async def root():
    return FileResponse(os.path.join(web_dir, "index.html"))

# Монтируем Socket.IO приложение
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

if __name__ == "__main__":
    import uvicorn
    import subprocess
    import tempfile
    
    # Предварительная проверка прав до старта сервера
    asyncio.run(plugin_manager.pre_check_elevation())
    
    # 1. Извлекаем ключи из базы данных или генерируем их
    ssl_cert = config_manager.get_secret("SSL_CERT")
    ssl_key = config_manager.get_secret("SSL_KEY")
    
    if not ssl_cert or not ssl_key:
        logger.info("SSL-сертификаты не найдены в БД. Автоматическая генерация...")
        try:
            # Создаем временную папку для генерации
            with tempfile.TemporaryDirectory() as tmpdir:
                cnf_path = os.path.join(tmpdir, "openssl.cnf")
                tmp_key = os.path.join(tmpdir, "key.pem")
                tmp_cert = os.path.join(tmpdir, "cert.pem")
                
                # Пишем локальный конфиг для openssl
                with open(cnf_path, "w", encoding="utf-8") as f:
                    f.write("[req]\ndistinguished_name = req_distinguished_name\nprompt = no\n\n[req_distinguished_name]\nCN = localhost\n")
                
                # Запускаем генерацию
                subprocess.run([
                    "openssl", "req", "-x509", "-newkey", "rsa:4096",
                    "-keyout", tmp_key, "-out", tmp_cert,
                    "-sha256", "-days", "3650", "-nodes",
                    "-config", cnf_path
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # Читаем результаты
                with open(tmp_cert, "r", encoding="utf-8") as f:
                    ssl_cert = f.read()
                with open(tmp_key, "r", encoding="utf-8") as f:
                    ssl_key = f.read()
                
                # Сохраняем зашифрованными в базу данных
                config_manager.set_secret("SSL_CERT", ssl_cert)
                config_manager.set_secret("SSL_KEY", ssl_key)
                
            logger.info("SSL-сертификаты успешно сгенерированы и сохранены в БД!")
        except Exception as e:
            logger.error(f"Критическая ошибка при автогенерации SSL-сертификатов: {e}")
            raise e
            
    # 2. Создаем временную директорию keys для Uvicorn в BASE_DIR
    from core.config import BASE_DIR
    keys_dir = os.path.join(BASE_DIR, "keys")
    if not os.path.exists(keys_dir):
        os.makedirs(keys_dir)
        
    key_path = os.path.join(keys_dir, "key.pem")
    cert_path = os.path.join(keys_dir, "cert.pem")
    
    # Записываем временные файлы из БД для старта Uvicorn
    with open(cert_path, "w", encoding="utf-8") as f:
        f.write(ssl_cert)
    with open(key_path, "w", encoding="utf-8") as f:
        f.write(ssl_key)
        
    try:
        # Запускаем сервер строго по HTTPS / WSS
        logger.info("Запуск сервера MonitHome по защищенному протоколу HTTPS...")
        uvicorn.run(
            socket_app,
            host="0.0.0.0",
            port=5000,
            log_level="info",
            ssl_keyfile=key_path,
            ssl_certfile=cert_path
        )
    finally:
        # Удаляем временные файлы с диска после остановки сервера
        logger.info("Очистка временных SSL-файлов с диска...")
        if os.path.exists(cert_path):
            try: os.remove(cert_path)
            except: pass
        if os.path.exists(key_path):
            try: os.remove(key_path)
            except: pass
        if os.path.exists(keys_dir):
            try: os.rmdir(keys_dir)
            except: pass
