import logging

logger = logging.getLogger("SocketHandlers")

async def check_auth(sio, sid):
    """Проверяет, авторизован ли клиент (находится ли он в комнате authorized)"""
    if 'authorized' not in sio.rooms(sid):
        logger.warning(f"Unauthorized access attempt from {sid}. Blocking.")
        await sio.emit('auth_required', room=sid)
        return False
    return True
