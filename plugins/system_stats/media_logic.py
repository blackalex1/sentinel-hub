import asyncio
import os
import sys
import json
from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as SessionManager

async def get_media_info():
    try:
        sessions = await SessionManager.request_async()
        current_session = sessions.get_current_session()
        
        if current_session:
            info = await current_session.try_get_media_properties_async()
            return {
                "title": info.title,
                "artist": info.artist,
                "album": info.album_title,
                "player": current_session.source_app_user_model_id,
                "status": "playing"
            }
    except Exception as e:
        return {"error": str(e)}
    return None

def get_stats():
    # Эта функция будет вызываться нашим основным сервисом
    media = asyncio.run(get_media_info())
    return {
        "media": media
    }

if __name__ == "__main__":
    # Тестовый запуск с корректной кодировкой для консоли
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    res = get_stats()
    print(json.dumps(res, indent=2, ensure_ascii=False))
