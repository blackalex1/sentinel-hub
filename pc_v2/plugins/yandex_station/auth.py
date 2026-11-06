import re
import time
import json
import asyncio
import aiohttp
from zeroconf import ServiceBrowser, Zeroconf
from .const import CLIENT_ID, CLIENT_SECRET
from .discovery import SpeakerDiscovery, get_all_interfaces

class YandexAuth:
    def __init__(self, plugin):
        self.plugin = plugin
        self.log = plugin.log

    def get_secret(self, key: str, default: str = "") -> str:
        """Получение секрета через плагин (из зашифрованной БД)"""
        return self.plugin.get_secret(key, default)

    def set_secret(self, key: str, value: str):
        """Сохранение секрета через плагин (в зашифрованную БД)"""
        self.plugin.set_secret(key, value)

    def has_token(self):
        token = self.get_secret("YANDEX_TOKEN", "")
        return len(token) > 10

    async def start_qr_login(self):
        if getattr(self.plugin, "_qr_status", "") in ["getting_url", "waiting"]:
            return
        self.plugin._qr_status = "getting_url"
        asyncio.create_task(self._qr_login_worker())

    async def _emit_qr_status(self):
        if not getattr(self.plugin, "_qr_status", ""):
            return
            
        status_text = self.plugin.i18n("qr_waiting", "Ожидание...")
        if self.plugin._qr_status == "getting_url": status_text = self.plugin.i18n("loading", "Загрузка...")
        elif self.plugin._qr_status == "success": status_text = self.plugin.i18n("qr_success", "Успешно!")
        elif self.plugin._qr_status == "error": status_text = self.plugin.i18n("qr_error", "Ошибка")

        data = {
            "qr_url": getattr(self.plugin, "_qr_image_base64", ""),
            "status": status_text,
            "instructions": self.plugin.i18n("scan_qr", "Отсканируйте код")
        }
        await self.plugin.emit_event("show_qr", data)

    async def _qr_login_worker(self):
        self.log("Starting Yandex QR Login worker...")
        try:
            async with aiohttp.ClientSession() as session:
                session.headers.update({
                    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                })

                # 1. CSRF
                self.log("Step 1: Fetching CSRF token...")
                async with session.get("https://passport.yandex.ru/am?app_platform=android", timeout=10) as r:
                    text = await r.text()
                    m = re.search(r'"csrf_token" value="([^"]+)"', text)
                    if not m: m = re.search(r'hal.CSRF\s*=\s*["\']([^"\']+)["\']', text) # Fallback pattern
                    if not m: m = re.search(r'window\.__CSRF__\s*=\s*["\']([^"\']+)["\']', text)
                    if not m:
                        self.log("Step 1 Failed: CSRF token not found in response", 40)
                        self.plugin._qr_status = "error"
                        await self._emit_qr_status()
                        return
                    page_csrf = m.group(1)
                    self.log(f"Step 1 Success: CSRF found ({page_csrf[:5]}...)")

                bff_headers = {
                    "X-CSRF-Token": page_csrf,
                    "Origin": "https://passport.yandex.ru",
                    "Referer": "https://passport.yandex.ru/pwl-yandex",
                }

                # 2. Multistep start
                self.log("Step 2: Starting multistep auth...")
                async with session.post("https://passport.yandex.ru/pwl-yandex/api/passport/auth/multistep_start", headers=bff_headers, data={}, timeout=10) as r_start:
                    resp_start = await r_start.json()
                    track_id = resp_start.get("track_id")
                    if not track_id:
                        self.log(f"Step 2 Failed: No track_id in response: {resp_start}", 40)
                        self.plugin._qr_status = "error"
                        return
                    self.log(f"Step 2 Success: Track ID obtained ({track_id[:5]}...)")

                # 3. Request QR session
                self.log("Step 3: Submitting password/code request...")
                async with session.post("https://passport.yandex.ru/pwl-yandex/api/passport/auth/password/submit", headers=bff_headers, data={"track_id": track_id, "with_code": 1, "retpath": "https://passport.yandex.ru/profile"}, timeout=10) as r_qr:
                    qr_resp = await r_qr.json()
                    polling_csrf = qr_resp.get("csrf_token", page_csrf)
                    self.log("Step 3 Success: QR session requested")

                qr_url = f"https://passport.yandex.ru/auth/magic/code/?track_id={track_id}"
                self.plugin._qr_url = qr_url
                self.plugin._qr_status = "getting_url"
                await self._emit_qr_status()

                self.log(f"Step 4: Fetching QR image/SVG from {qr_url}...")
                try:
                    import base64
                    async with session.get(qr_url, timeout=10) as r_page:
                        page_text = await r_page.text()
                        svg_match = re.search(r'<svg[^>]*>.*?</svg>', page_text, re.DOTALL)
                        
                        if svg_match:
                            self.log("Step 4: Found SVG QR code")
                            svg_content = svg_match.group(0)
                            b64_data = base64.b64encode(svg_content.encode('utf-8')).decode()
                            self.plugin._qr_image_base64 = f"data:image/svg+xml;base64,{b64_data}"
                        else:
                            self.log("Step 4: SVG not found, falling back to image...")
                            async with session.get(f"https://passport.yandex.ru/auth/magic/code/image?track_id={track_id}", timeout=10) as img_r:
                                if img_r.status == 200:
                                    img_content = await img_r.read()
                                    b64_data = base64.b64encode(img_content).decode()
                                    self.plugin._qr_image_base64 = f"data:image/png;base64,{b64_data}"
                                    self.log("Step 4: Found PNG QR code")
                                else:
                                    self.log(f"Step 4 Failed: Image request status {img_r.status}", 40)
                except Exception as e:
                    self.log(f"Step 4 Exception: {e}", 30)

                self.plugin._qr_status = "waiting"
                await self._emit_qr_status()

                # 4. Polling
                start_time = time.time()
                while time.time() - start_time < 300:
                    try:
                        async with session.post("https://passport.yandex.ru/auth/new/magic/status/", data={"csrf_token": polling_csrf, "track_id": track_id}, timeout=10) as status_r:
                            status_resp = await status_r.json()
                            if status_resp.get("status") == "ok":
                                cookies_str = "; ".join([f"{k}={v.value}" for k, v in session.cookie_jar.filter_cookies("https://passport.yandex.ru").items()])
                                async with session.post("https://mobileproxy.passport.yandex.net/1/bundle/oauth/token_by_sessionid", 
                                                    data={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}, 
                                                    headers={"Ya-Client-Host": "passport.yandex.ru", "Ya-Client-Cookie": cookies_str},
                                                    timeout=10) as token_r:
                                    x_token = (await token_r.json()).get("access_token")
                                    if x_token:
                                        self.set_secret("YANDEX_TOKEN", x_token)
                                        self.log("Yandex token saved successfully to Database.")
                                        self.plugin._qr_status = "success"
                                        await self._emit_qr_status()
                                        await self.plugin.broadcaster.broadcast_config_to_tablet()
                                        asyncio.create_task(self.refresh_tokens_sync())
                                        return
                            elif status_resp.get("status") == "error":
                                break
                    except Exception as e:
                        pass
                    await asyncio.sleep(3)
                
                self.plugin._qr_status = "error"
                await self._emit_qr_status()

        except Exception as e:
            self.log(f"QR Login worker exception: {e}", 40)
            self.plugin._qr_status = "error"
            await self._emit_qr_status()

    async def refresh_tokens_sync(self):
        now = time.time()
        if getattr(self.plugin, "_refreshing_tokens", False) or (now - getattr(self.plugin, "_last_refresh_time", 0) < 10): 
            return False
        self.plugin._refreshing_tokens = True
        self.plugin._last_refresh_time = now
        self.log("Starting automatic token refresh cycle...")
        
        try:
            x_token = self.get_secret("YANDEX_TOKEN")
            if not x_token: return False

            # Zeroconf поиск делаем в пуле потоков, так как библиотека синхронная
            def run_zeroconf():
                interfaces = get_all_interfaces()
                zeroconf = Zeroconf(interfaces=interfaces)
                discovery = SpeakerDiscovery()
                browser = ServiceBrowser(zeroconf, "_yandexio._tcp.local.", discovery)
                time.sleep(7)
                browser.cancel()
                zeroconf.close()
                return discovery.found_devices

            local_devices = await asyncio.to_thread(run_zeroconf)

            headers = {"Authorization": f"OAuth {x_token}", "X-Yandex-Token": x_token, "User-Agent": "Mozilla/5.0"}
            
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get("https://quasar.yandex.net/glagol/device_list", timeout=10) as r:
                    if r.status != 200: 
                        async with session.get("https://quasar.yandex.ru/glagol/device_list", timeout=10) as r2:
                            data = await r2.json() if r2.status == 200 else {}
                    else:
                        data = await r.json()
                        
                quasar_list = data.get("devices", [])
                if not quasar_list: return False
                
                new_results = {}
                for q_dev in quasar_list:
                    d_id = q_dev.get("id", "").strip()
                    if not d_id: continue
                    g_token = q_dev.get("glagol_token") or q_dev.get("glagol", {}).get("token")
                    
                    if not g_token:
                        url_single = f"https://quasar.yandex.ru/glagol/token?device_id={d_id}&platform={q_dev.get('platform')}"
                        try:
                            async with session.get(url_single, timeout=5) as r_s:
                                if r_s.status == 200: g_token = (await r_s.json()).get("token")
                        except: pass
                        
                    if not g_token: continue
                    ip = local_devices.get(d_id, {}).get("ip") or self.plugin.devices.get(d_id, {}).get("ip")
                    if ip:
                        new_results[d_id] = {"name": q_dev.get("name", "Колонка").strip(), "glagol_token": g_token, "platform": q_dev.get("platform"), "ip": ip}
                
                if new_results:
                    self.set_secret("GLAGOL_TOKENS", json.dumps(new_results, ensure_ascii=False))
                    self.plugin.devices = new_results
                    # Принудительно применяем новый конфиг (запуск воркеров, рассылка на планшеты)
                    await self.plugin.device_manager.apply_mode()
                    return True
        except Exception as e: 
            self.log(f"Auto-refresh exception: {e}", 40)
        finally: 
            self.plugin._refreshing_tokens = False
        return False
