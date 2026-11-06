import asyncio
import json
import os
import ssl
import time
import uuid
import requests
import websockets
import re
import binascii
import ipaddress
from zeroconf import ServiceBrowser, Zeroconf

# --- КОНФИГУРАЦИЯ ---
# Thanks to https://github.com/MarshalX/yandex-music-api/
CLIENT_ID = "23cabbbdc6cd418abb4b39c32c41195d"
CLIENT_SECRET = "53bc75238f0c4d08a118e51fe9203300"
TOKENS_FILE = "glagol_tokens.json"
AUTH_FILE = ".env"

# --- ЛОГИКА АВТОРИЗАЦИИ (КОПИЯ ИЗ РАБОЧЕГО QR_LOGIN.PY) ---
def get_x_token_from_env():
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, "r") as f:
            for line in f:
                if line.startswith("YANDEX_TOKEN="):
                    return line.split("=")[1].strip()
    return None

def qr_login_sync():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    })

    print("\n[1/4] Получение CSRF токена страницы...")
    r = session.get("https://passport.yandex.ru/am?app_platform=android")
    m = re.search(r'"csrf_token" value="([^"]+)"', r.text)
    if not m: m = re.search(r'window\.__CSRF__\s*=\s*["\']([^"\']+)["\']', r.text)
    if not m: return None
    page_csrf = m.group(1)

    bff_headers = {
        "X-CSRF-Token": page_csrf,
        "Origin": "https://passport.yandex.ru",
        "Referer": "https://passport.yandex.ru/pwl-yandex",
    }

    print("[2/4] Старт мультишаговой авторизации...")
    r_start = session.post("https://passport.yandex.ru/pwl-yandex/api/passport/auth/multistep_start", headers=bff_headers, data={})
    track_id = r_start.json().get("track_id")

    print("[3/4] Запрос сессии для QR-кода...")
    r_qr = session.post("https://passport.yandex.ru/pwl-yandex/api/passport/auth/password/submit", headers=bff_headers, data={"track_id": track_id, "with_code": 1, "retpath": "https://passport.yandex.ru/profile"})
    qr_resp = r_qr.json()
    polling_csrf = qr_resp.get("csrf_token", page_csrf)

    qr_url = f"https://passport.yandex.ru/auth/magic/code/?track_id={track_id}"
    print("\n" + "="*60)
    print("ОТКРОЙ ЭТУ ССЫЛКУ И ОТСКАНЕРУЙ QR-КОД ТЕЛЕФОНОМ:")
    print(qr_url)
    print("="*60 + "\n")
    print("Ожидание подтверждения...")

    start_time = time.time()
    while time.time() - start_time < 300:
        try:
            status_r = session.post("https://passport.yandex.ru/auth/new/magic/status/", data={"csrf_token": polling_csrf, "track_id": track_id})
            status_resp = status_r.json()
            if status_resp.get("status") == "ok":
                print("\n[!] Подтверждено! Получаем X-Token...")
                cookies_str = "; ".join([f"{k}={v}" for k, v in session.cookies.get_dict().items()])
                token_r = session.post("https://mobileproxy.passport.yandex.net/1/bundle/oauth/token_by_sessionid", data={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}, headers={"Ya-Client-Host": "passport.yandex.ru", "Ya-Client-Cookie": cookies_str})
                x_token = token_r.json().get("access_token")
                if x_token:
                    with open(AUTH_FILE, "w") as f: f.write(f"YANDEX_TOKEN={x_token}\n")
                    print("[+] Успех! Токен сохранен.")
                    return x_token
            elif status_resp.get("status") == "wait":
                print(".", end="", flush=True)
        except: pass
        time.sleep(3)
    return None

# --- ЛОГИКА ПОИСКА КОЛОНОК ---
class SpeakerDiscovery:
    def __init__(self):
        self.found_devices = {}

    def remove_service(self, zeroconf, type, name): pass
    def update_service(self, zeroconf, type, name): pass

    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info:
            addresses = [str(ipaddress.ip_address(addr)) for addr in info.addresses]
            props = {k.decode(): v.decode() if isinstance(v, bytes) else v for k, v in info.properties.items()}
            device_id = props.get("deviceId")
            if device_id:
                self.found_devices[device_id] = {
                    "ip": addresses[0],
                    "port": info.port,
                    "platform": props.get("platform"),
                    "name": name.split(".")[0]
                }

async def discover_speakers(timeout=5):
    print(f"\n[2/4] Поиск колонок в сети (ждем {timeout} сек)...")
    zeroconf = Zeroconf()
    discovery = SpeakerDiscovery()
    browser = ServiceBrowser(zeroconf, "_yandexio._tcp.local.", discovery)
    await asyncio.sleep(timeout)
    zeroconf.close()
    return discovery.found_devices

# --- ЛОГИКА ПОЛУЧЕНИЯ ТОКЕНОВ ---
async def fetch_glagol_tokens(x_token, devices):
    print("\n[3/4] Запрос Glagol-токенов у Яндекса...")
    headers = {
        "Authorization": f"OAuth {x_token}",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "X-Yandex-Token": x_token
    }
    
    r = requests.get("https://quasar.yandex.net/glagol/device_list", headers=headers)
    if r.status_code != 200:
        print(f"Ошибка получения списка (.net): {r.status_code}. Пробуем .ru...")
        r = requests.get("https://quasar.yandex.ru/glagol/device_list", headers=headers)

    if r.status_code != 200:
        print(f"Ошибка получения списка: {r.status_code}")
        return {}
    
    quasar_list = r.json().get("devices", []) # БЫЛО "list", СТАЛО "devices"
    results = {}
    
    for q_dev in quasar_list:
        d_id = q_dev.get("id")
        name = q_dev.get("name")
        platform = q_dev.get("platform")
        g_token = q_dev.get("glagol_token")
        
        if not g_token:
            url_single = f"https://quasar.yandex.ru/glagol/token?device_id={d_id}&platform={platform}"
            r_single = requests.get(url_single, headers=headers)
            if r_single.status_code == 200:
                g_token = r_single.json().get("token")
        
        if g_token and devices.get(d_id, {}).get("ip"): # Фильтр: есть ключ И есть IP в сети
            results[d_id] = {
                "name": name.strip(),
                "glagol_token": g_token,
                "platform": platform,
                "ip": devices.get(d_id, {}).get("ip")
            }
            print(f"  [+] Колонку '{name.strip()}' можно контролировать локально.")
            
    if not results:
        print("\n[!] ВАЖНО: Ни одна из твоих колонок не найдена в локальной сети через mDNS.")
        print("Проверь, что компьютер и колонки подключены к одной Wi-Fi сети.")
        return {}

    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return results

# --- ЛОГИКА ТЕСТА ---
async def test_speaker(device_id, device_data):
    ip = device_data.get("ip")
    if not ip:
        print(f"\n[!] Ошибка: Неизвестен IP для колонки {device_data['name']}. Проверь Wi-Fi.")
        return

    print(f"\n[4/4] Тестируем колонку '{device_data['name']}' ({ip})...")
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        async with websockets.connect(f"wss://{ip}:1961", ssl=ssl_context) as ws:
            payload = {
                "conversationToken": device_data["glagol_token"],
                "id": str(uuid.uuid4()),
                "sentTime": int(round(time.time() * 1000)),
                "payload": {
                    "command": "sendText",
                    "text": "скажи локальное управление настроено успешно"
                }
            }
            await ws.send(json.dumps(payload))
            print("  [+] Команда отправлена. Слушай колонку!")
            await asyncio.sleep(2)
    except Exception as e:
        print(f"  [-] Ошибка теста: {e}")

# --- MAIN ---
async def main():
    print("=== YANDEX STATION SETUP TOOL ===")
    
    x_token = get_x_token_from_env()
    
    if not x_token:
        # Запускаем синхронную авторизацию (так как requests не async)
        x_token = await asyncio.to_thread(qr_login_sync)
    else:
        print("[+] X-Token найден в .env")

    if not x_token: return

    local_devices = await discover_speakers()
    glagol_data = await fetch_glagol_tokens(x_token, local_devices)
    
    if not glagol_data:
        print("Не удалось получить данные о колонках.")
        return

    print("\nДОСТУПНЫЕ КОЛОНКИ:")
    ids = list(glagol_data.keys())
    for i, d_id in enumerate(ids):
        d = glagol_data[d_id]
        ip_str = f" [IP: {d['ip']}]" if d['ip'] else " [IP НЕ НАЙДЕН]"
        print(f"{i+1}. {d['name']} ({d['platform']}){ip_str}")

    try:
        choice = input("\nВыбери номер колонки для теста (Enter - выход): ")
        if choice:
            choice = int(choice) - 1
            if 0 <= choice < len(ids):
                target_id = ids[choice]
                await test_speaker(target_id, glagol_data[target_id])
    except:
        pass

if __name__ == "__main__":
    asyncio.run(main())
