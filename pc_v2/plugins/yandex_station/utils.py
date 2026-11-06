import ssl
import time

def get_ssl_ctx():
    """Создает SSL контекст без проверки сертификатов для Glagol API"""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def parse_state(s):
    """Парсит сырое состояние от Яндекс Станции в удобный формат"""
    p = s.get("playerState", {})
    extra = p.get("extra", {})
    
    title = p.get("title") or extra.get("title") or ""
    
    # Разбираем список артистов для коллабораций
    artists_list = []
    artists_raw = extra.get("artists") or p.get("artists")
    if isinstance(artists_raw, list):
        for art in artists_raw:
            if isinstance(art, dict) and art.get("name"):
                artists_list.append(art["name"])
                
    if artists_list:
        artist = ", ".join(artists_list)
    else:
        artist = p.get("subtitle") or extra.get("artist") or ""
        
    track_id = p.get("id") or extra.get("id") or ""
    
    cover = ""
    cover_raw = extra.get("coverURI")
    if cover_raw:
        cover = "https://" + cover_raw.replace("%%", "400x400")

    progress = p.get("progress", 0)
    duration = p.get("duration", 0)
    
    # Нормализация: если значение > 10000, это скорее всего миллисекунды
    if progress > 10000: progress /= 1000.0
    if duration > 10000: duration /= 1000.0

    return {
        "volume": round(s.get("volume", 0) * 100),
        "playing": s.get("playing", False) or p.get("status") == "playing",
        "title": title,
        "artist": artist,
        "cover": cover,
        "track_id": track_id,
        "progress": progress,
        "duration": duration,
        "last_update": time.time(),
        "alice_state": s.get("aliceState", "IDLE")
    }
