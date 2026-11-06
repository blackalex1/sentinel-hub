
import asyncio
import json
import base64
import sys
import io
import time
from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as SessionManager
from winsdk.windows.storage.streams import DataReader

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def main_loop():
    import datetime
    last_info = {"title": "", "artist": "", "playing": False, "cover": None, "duration": 0.0, "progress": 0.0}
    is_first_run = True
    manager = await SessionManager.request_async()
    while True:
        try:
            sessions = manager.get_sessions()
            session = manager.get_current_session()
            if not session or (session.get_playback_info().playback_status != 4):
                for s in sessions:
                    if s.get_playback_info().playback_status == 4:
                        session = s
                        break
            if not session and sessions: session = sessions[0]
            if session:
                pb = session.get_playback_info()
                props = await session.try_get_media_properties_async()
                timeline = session.get_timeline_properties()
                
                title, artist = props.title or "", props.artist or props.album_artist or ""
                playing = pb.playback_status == 4 if pb else False
                
                # Магия интерполяции Windows:
                duration = timeline.end_time.total_seconds() if timeline else 0.0
                progress = 0.0
                if timeline:
                    base_pos = timeline.position.total_seconds()
                    if playing:
                        now = datetime.datetime.now(datetime.timezone.utc)
                        lut = timeline.last_updated_time
                        # Если вдруг пришло naive (хотя в winsdk обычно aware), конвертируем
                        if lut.tzinfo is None:
                            lut = lut.replace(tzinfo=datetime.timezone.utc)
                        
                        now_offset = (now - lut).total_seconds()
                        # Ограничиваем смещение, чтобы не было скачков при лагах системы
                        progress = min(duration, base_pos + max(0, now_offset))
                    else:
                        progress = base_pos

                if not title and playing: title = "Медиа"
                if title != last_info.get("title") or artist != last_info.get("artist"):
                    img = None
                    # Пытаемся захватить обложку (делаем больше попыток для медленных источников)
                    for attempt in range(5):
                        if props.thumbnail:
                            try:
                                stream = await props.thumbnail.open_read_async()
                                reader = DataReader(stream.get_input_stream_at(0))
                                await reader.load_async(stream.size)
                                raw_data = bytes(reader.read_buffer(stream.size))
                                
                                # Кодируем сырые байты в base64 и шлем напрямую
                                img = base64.b64encode(raw_data).decode('utf-8')
                                
                                if img: 
                                    print(json.dumps({"log": f"Captured raw cover: {len(img)} bytes"}, ensure_ascii=False), flush=True)
                                    break
                            except Exception as e:
                                print(json.dumps({"log": f"Cover capture error: {str(e)}"}, ensure_ascii=False), flush=True)
                        else:
                            # Если thumbnail еще нет, ждем
                            pass
                        await asyncio.sleep(0.5) 
                
                info = {
                    "title": title, "artist": artist, "playing": playing, 
                    "cover": img, "duration": duration, "progress": progress,
                    "last_update": time.time()
                }
                
                # Шлем данные если что-то изменилось ИЛИ прошло много времени (5 сек для синхронизации)
                is_changed = (info["title"] != last_info.get("title") or 
                             info["artist"] != last_info.get("artist") or 
                             info["playing"] != last_info.get("playing"))
                
                # Порог 5 секунд — этого достаточно, чтобы подправить часы, но не грузить сеть
                is_time_tick = playing and abs(info["progress"] - last_info.get("progress", 0)) > 5.0

                if is_changed or is_time_tick or is_first_run:
                    print(json.dumps(info, ensure_ascii=False), flush=True)
                    last_info = info
                    is_first_run = False
            else:
                if last_info.get("title") != "":
                    print(json.dumps({"title": "", "artist": "", "playing": False, "cover": None, "duration": 0.0, "progress": 0.0, "last_update": time.time()}, ensure_ascii=False), flush=True)
                    last_info = {"title": "", "artist": "", "playing": False, "cover": None, "duration": 0.0, "progress": 0.0}
        except Exception as e: 
            pass
        await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(main_loop())
