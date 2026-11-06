import logging
from .base import check_auth
from plugin_engine.manager import plugin_manager

logger = logging.getLogger("SocketHandlers.Plugins")

def register_plugin_handlers(sio):
    @sio.on("get_yandex_config")
    async def handle_get_yandex_config(sid):
        if sid is not None and not await check_auth(sio, sid): return
        p = plugin_manager.active_plugins.get("yandex_station")
        if p:
            await p.handle_command("get_yandex_config", {"sid": sid})

    @sio.on("plugin_command")
    async def handle_plugin_command(sid, data):
        if not await check_auth(sio, sid): return
        p_id = data.get('plugin_id')
        action = data.get('action')
        target = data.get('target')
        p_data = data.get('data')
        
        final_data = {}
        if isinstance(p_data, dict):
            final_data.update(p_data)
        elif p_data is not None:
            final_data['value'] = p_data
            
        if target:
            final_data['device_id'] = target
        
        if p_id and action:
            await plugin_manager.handle_command(p_id, action, final_data)
