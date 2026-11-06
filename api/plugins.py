import os
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from core.config import config_manager
from plugin_engine.manager import plugin_manager
from core.event_bus import event_bus
from .security import verify_token

router = APIRouter(prefix="/api/plugins")

class PluginToggleRequest(BaseModel):
    plugin_id: str
    active: bool

class PluginConfigRequest(BaseModel):
    config_data: dict

@router.get("", dependencies=[Depends(verify_token)])
async def get_plugins():
    # Используем абсолютный путь к директории плагинов
    from core.config import BUNDLE_DIR
    plugins_dir = os.path.join(BUNDLE_DIR, "plugins")
    cfg = config_manager.get()
    active_plugins = cfg.active_plugins
    
    result = []
    if os.path.exists(plugins_dir):
        for p_id in os.listdir(plugins_dir):
            p_path = os.path.join(plugins_dir, p_id)
            if not os.path.isdir(p_path) or p_id.startswith("__"): continue
                
            p_cfg_path = os.path.join(p_path, "config.json")
            if os.path.exists(p_cfg_path):
                try:
                    with open(p_cfg_path, "r", encoding="utf-8") as f:
                        p_cfg = json.load(f)
                        if p_cfg.get("hidden", False): continue
                        instance = plugin_manager.active_plugins.get(p_id)
                        needs_elevation = getattr(instance, "needs_elevation", False) if instance else False
                        elevation_active = getattr(instance, "elevation_active", False) if instance else False
                        
                        result.append({
                            "id": p_id, "active": p_id in active_plugins,
                            "name": p_cfg.get("name", p_id.replace("_", " ").title()),
                            "description": p_cfg.get("description", ""),
                            "version": p_cfg.get("version", "1.0.0"),
                            "has_settings": p_cfg.get("has_settings", False),
                            "needs_elevation": needs_elevation,
                            "elevation_active": elevation_active
                        })
                except: pass
    return {"plugins": result}

@router.post("/toggle", dependencies=[Depends(verify_token)])
async def toggle_plugin(req: PluginToggleRequest):
    cfg = config_manager.get()
    active_plugins = set(cfg.active_plugins)
    if req.active:
        active_plugins.add(req.plugin_id)
        await plugin_manager.start_plugin(req.plugin_id)
    else:
        active_plugins.discard(req.plugin_id)
        await plugin_manager.stop_plugin(req.plugin_id)
    config_manager.config.active_plugins = list(active_plugins)
    config_manager.save()
    await event_bus.emit("ui_config_changed", {"plugin_id": req.plugin_id, "active": req.active})
    return {"success": True, "active": req.active}

@router.get("/{plugin_id}/config", dependencies=[Depends(verify_token)])
async def get_plugin_config(plugin_id: str):
    from core.config import BUNDLE_DIR
    p_cfg_path = os.path.join(BUNDLE_DIR, "plugins", plugin_id, "config.json")
    default_config = {}
    if os.path.exists(p_cfg_path):
        with open(p_cfg_path, "r", encoding="utf-8") as f:
            default_config = json.load(f)
    return config_manager.get_plugin_config(plugin_id, default_config)

@router.post("/{plugin_id}/config", dependencies=[Depends(verify_token)])
async def save_plugin_config(plugin_id: str, req: PluginConfigRequest):
    config_manager.save_plugin_config(plugin_id, req.config_data)
    p = plugin_manager.active_plugins.get(plugin_id)
    if p:
        if plugin_id == "system_stats" and "enabled_sensors" in req.config_data:
            await p.handle_command("update_sensor_settings", req.config_data["enabled_sensors"])
        else:
            await p.handle_command("update_settings", req.config_data)
    await event_bus.emit("ui_config_changed", {"plugin_id": plugin_id})
    return {"success": True}
