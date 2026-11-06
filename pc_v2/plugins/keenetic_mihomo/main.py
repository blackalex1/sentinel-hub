import asyncio
import hashlib
import json
import logging
import time
import aiohttp
from plugin_engine.base_plugin import BasePlugin

class Plugin(BasePlugin):
    """
    Интегрированный плагин Keenetic & Mihomo (Clash Meta).
    Отслеживает сетевой статус, клиентов сети роутера Keenetic и
    управляет прокси-сервером Mihomo с безопасным шифрованием паролей.
    """
    def __init__(self, plugin_id: str):
        super().__init__(plugin_id)
        self.session = None
        self.router_ip = ""
        self.mihomo_api_url = ""
        self.prev_rx = 0
        self.prev_tx = 0
        self.prev_time = 0
        self.latest_mihomo_traffic = {"down_speed_mbits": 0.0, "up_speed_mbits": 0.0}
        self.session_cookie = ""
        self.router_model = ""
        
        self._monitoring_task = None
        self._traffic_listener_task = None

    async def on_start(self):
        config = self.get_config()
        self.router_ip = config.get("router_ip", "192.168.1.1")
        mihomo_port = config.get("mihomo_port", 9097)
        self.mihomo_api_url = f"http://{self.router_ip}:{mihomo_port}"
        
        self.session = aiohttp.ClientSession()
        self.log(f"Keenetic & Mihomo integration starting. Target: {self.router_ip}")
        
        self._monitoring_task = self.create_task(self._monitoring_loop())
        self._traffic_listener_task = self.create_task(self._mihomo_traffic_listener())

    async def on_stop(self):
        if self._monitoring_task:
            self._monitoring_task.cancel()
        if self._traffic_listener_task:
            self._traffic_listener_task.cancel()
            
        if self.session:
            await self.session.close()
            
        self.log("Keenetic & Mihomo integration stopped.")

    def _get_headers(self) -> dict:
        """Формирование заголовков авторизации для Mihomo API"""
        headers = {}
        secret = self.get_secret("MIHOMO_SECRET", "")
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        return headers

    def _get_keenetic_headers(self) -> dict:
        """Формирование заголовков авторизации (Cookie) для Keenetic RCI API"""
        headers = {}
        if self.session_cookie:
            headers["Cookie"] = self.session_cookie
        return headers

    async def _authenticate_keenetic(self) -> bool:
        """Авторизация в Keenetic RCI с использованием MD5 + SHA256 (KeeneticOS 3.x/4.x+)"""
        config = self.get_config()
        login = config.get("router_login", "admin")
        password = self.get_secret("KEENETIC_PASSWORD", "")

        try:
            headers = {}
            if self.session_cookie:
                headers["Cookie"] = self.session_cookie

            async with self.session.get(f"http://{self.router_ip}/auth", headers=headers, timeout=3.0) as resp:
                if resp.status == 200:
                    return True # Уже авторизованы
                
                challenge = resp.headers.get("X-NDM-Challenge") or resp.headers.get("X-NDMS-Challenge")
                realm = resp.headers.get("X-NDM-Realm") or resp.headers.get("X-NDMS-Realm") or "Keenetic"
                cookie = resp.headers.get("Set-Cookie")
                if cookie:
                    self.session_cookie = cookie.split(";")[0]
                
                if not challenge:
                    return False

            if not password:
                return False

            # Расчёт хэша по стандарту Keenetic
            stage1 = f"{login}:{realm}:{password}"
            md5_hex = hashlib.md5(stage1.encode('utf-8')).hexdigest()
            stage2 = challenge + md5_hex
            sha256_hex = hashlib.sha256(stage2.encode('utf-8')).hexdigest()

            headers = {}
            if self.session_cookie:
                headers["Cookie"] = self.session_cookie

            auth_data = {"login": login, "password": sha256_hex}
            async with self.session.post(f"http://{self.router_ip}/auth", json=auth_data, headers=headers, timeout=3.0) as resp:
                if resp.status == 200:
                    cookie = resp.headers.get("Set-Cookie")
                    if cookie:
                        self.session_cookie = cookie.split(";")[0]
                    return True
        except Exception as e:
            self.log(f"Keenetic auth challenge error: {e}", level=logging.DEBUG)
        return False

    async def _test_keenetic_connection(self, ip, login, password) -> bool:
        """Тестовое подключение к Keenetic для верификации GUI-ввода с детальным выводом ошибок"""
        try:
            async with aiohttp.ClientSession() as temp_session:
                async with temp_session.get(f"http://{ip}/auth", timeout=3.0) as resp:
                    if resp.status == 200:
                        return True
                    
                    challenge = resp.headers.get("X-NDM-Challenge") or resp.headers.get("X-NDMS-Challenge")
                    realm = resp.headers.get("X-NDM-Realm") or resp.headers.get("X-NDMS-Realm") or "Keenetic"
                    cookie = resp.headers.get("Set-Cookie")
                    
                    if not challenge:
                        raise Exception("Устройство по указанному IP не вернуло авторизационный челлендж. Убедитесь, что это роутер Keenetic.")

                if not password:
                    raise Exception("Пароль не может быть пустым.")

                # Расчёт хэша
                stage1 = f"{login}:{realm}:{password}"
                md5_hex = hashlib.md5(stage1.encode('utf-8')).hexdigest()
                stage2 = challenge + md5_hex
                sha256_hex = hashlib.sha256(stage2.encode('utf-8')).hexdigest()

                headers = {}
                if cookie:
                    headers["Cookie"] = cookie.split(";")[0]

                auth_data = {"login": login, "password": sha256_hex}
                async with temp_session.post(f"http://{ip}/auth", json=auth_data, headers=headers, timeout=3.0) as resp:
                    if resp.status == 200:
                        return True
                    else:
                        raise Exception(f"Неверный логин или пароль администратора роутера (Код ответа: {resp.status})")
        except Exception as e:
            raise Exception(f"Ошибка проверки Keenetic: {str(e)}")

    async def _test_mihomo_connection(self, ip, port, secret) -> bool:
        """Тестовое подключение к Mihomo API для верификации GUI-ввода с детальным выводом ошибок"""
        try:
            headers = {}
            if secret:
                headers["Authorization"] = f"Bearer {secret}"
            
            async with aiohttp.ClientSession() as temp_session:
                async with temp_session.get(f"http://{ip}:{port}/configs", headers=headers, timeout=3.0) as resp:
                    if resp.status == 200:
                        return True
                    elif resp.status == 401:
                        raise Exception("Недействительный секретный токен Mihomo (ошибка авторизации 401).")
                    else:
                        raise Exception(f"API Mihomo вернуло код ошибки: {resp.status}")
        except Exception as e:
            raise Exception(f"Ошибка проверки Mihomo: {str(e)}")

    async def _mihomo_traffic_listener(self):
        """Фоновый слушатель потока трафика Mihomo в Mbps"""
        while True:
            try:
                headers = self._get_headers()
                # Слушаем непрерывный чанк-поток трафика
                async with self.session.get(f"{self.mihomo_api_url}/traffic", headers=headers, timeout=None) as resp:
                    if resp.status == 200:
                        async for chunk in resp.content:
                            try:
                                data = json.loads(chunk.decode('utf-8'))
                                self.latest_mihomo_traffic = {
                                    "down_speed_mbits": round((data.get("down", 0) * 8) / (1024 * 1024), 2),
                                    "up_speed_mbits": round((data.get("up", 0) * 8) / (1024 * 1024), 2)
                                }
                            except Exception:
                                pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log(f"Mihomo traffic listener disconnected: {e}", level=logging.DEBUG)
                self.latest_mihomo_traffic = {"down_speed_mbits": 0.0, "up_speed_mbits": 0.0}
            
            await asyncio.sleep(5.0) # Задержка перед повторным подключением

    async def _monitoring_loop(self):
        """Основной цикл мониторинга и сбора статистики"""
        while True:
            try:
                # 1. Попытка авторизации на роутере
                keenetic_online = await self._authenticate_keenetic()
                
                wan_speed_down = 0.0
                wan_speed_up = 0.0
                wan_uptime = 0
                clients = []
                repeaters = []
                
                if keenetic_online:
                    k_headers = self._get_keenetic_headers()
                    
                    # Запрос системной информации (модели, процессора и памяти)
                    cpu_load = 0
                    ram_usage = 0.0
                    try:
                        async with self.session.get(f"http://{self.router_ip}/rci/show/system", headers=k_headers) as resp:
                            if resp.status == 200:
                                sys_data = await resp.json()
                                if not self.router_model:
                                    self.router_model = sys_data.get("model", "")
                                
                                # Загрузка процессора
                                cpu_load = sys_data.get("cpuload", 0)
                                
                                # Использование памяти
                                memory_data = sys_data.get("memory", "")
                                if isinstance(memory_data, str) and "/" in memory_data:
                                    try:
                                        used, total = map(int, memory_data.split("/"))
                                        if total > 0:
                                            ram_usage = round((used / total) * 100, 1)
                                    except Exception:
                                        pass
                                elif isinstance(memory_data, dict):
                                    used = memory_data.get("used", 0)
                                    total = memory_data.get("total", 0)
                                    if total > 0:
                                        ram_usage = round((used / total) * 100, 1)
                    except Exception as e:
                        self.log(f"Failed to query router system info: {e}", level=logging.DEBUG)

                    # Запрос списка активных клиентов
                    async with self.session.get(f"http://{self.router_ip}/rci/show/ip/hotspot", headers=k_headers) as resp:
                        clients_data = await resp.json() if resp.status == 200 else {}
                        for c in clients_data.get("host", []):
                            if c.get("active", False):
                                clients.append({
                                    "name": c.get("hostname", c.get("name", "Неизвестное")),
                                    "ip": c.get("ip", ""),
                                    "mac": c.get("mac", ""),
                                    "ap": c.get("ap", "Кабель")
                                })

                    # Запрос участников Mesh Wi-Fi (mws/member)
                    try:
                        async with self.session.get(f"http://{self.router_ip}/rci/show/mws/member", headers=k_headers) as resp:
                            if resp.status == 200:
                                mws_data = await resp.json()
                                members_list = []
                                if isinstance(mws_data, list):
                                    members_list = mws_data
                                elif isinstance(mws_data, dict):
                                    members_list = mws_data.get("member", [])
                                
                                for m in members_list:
                                    repeaters.append({
                                        "name": m.get("description") or m.get("model") or m.get("cid") or "Ретранслятор",
                                        "ip": m.get("ip", ""),
                                        "mac": m.get("mac", ""),
                                        "online": m.get("active", True) or m.get("online", True)
                                    })
                    except Exception as e:
                        self.log(f"Failed to query MWS members: {e}", level=logging.DEBUG)

                    # Запрос трафика на основном интерфейсе (vlan2 - дефолтный WAN)
                    async with self.session.get(f"http://{self.router_ip}/rci/show/interface/GigabitEthernet0/vlan2", headers=k_headers) as resp:
                        wan_data = await resp.json() if resp.status == 200 else {}
                        rx_bytes = int(wan_data.get("rxbytes", 0))
                        tx_bytes = int(wan_data.get("txbytes", 0))
                        wan_uptime = wan_data.get("uptime", 0)
                        
                        curr_time = time.time()
                        if self.prev_time > 0 and rx_bytes > 0:
                            dt = curr_time - self.prev_time
                            wan_speed_down = round(((rx_bytes - self.prev_rx) * 8) / (1024 * 1024 * dt), 2)
                            wan_speed_up = round(((tx_bytes - self.prev_tx) * 8) / (1024 * 1024 * dt), 2)
                        
                        self.prev_rx = rx_bytes
                        self.prev_tx = tx_bytes
                        self.prev_time = curr_time

                # 2. Опрос состояния Mihomo
                mihomo_online = False
                mihomo_mode = "RULE"
                proxy_groups = {}
                delays = {}
                
                headers = self._get_headers()
                try:
                    async with self.session.get(f"{self.mihomo_api_url}/configs", headers=headers, timeout=2.0) as resp:
                        if resp.status == 200:
                            configs_data = await resp.json()
                            mihomo_mode = configs_data.get("mode", "rule").upper()
                            mihomo_online = True
                except Exception:
                    pass

                if mihomo_online:
                    async with self.session.get(f"{self.mihomo_api_url}/proxies", headers=headers, timeout=2.0) as resp:
                        if resp.status == 200:
                            proxies_root = await resp.json()
                            all_proxies = proxies_root.get("proxies", {})
                            
                            # Фильтруем селекторы
                            for name, info in all_proxies.items():
                                if info.get("type") in ["Selector", "URLTest", "Fallback"]:
                                    proxy_groups[name] = {
                                        "type": info.get("type"),
                                        "now": info.get("now"),
                                        "all": info.get("all", [])
                                    }
                            
                            # Извлекаем историю пингов
                            for name, info in all_proxies.items():
                                if info.get("type") not in ["Selector", "URLTest", "Fallback", "Direct", "Reject"]:
                                    history = info.get("history", [])
                                    last_delay = history[-1].get("delay", -1) if history else -1
                                    delays[name] = last_delay

                # Формируем и рассылаем состояние
                await self.emit_state({
                    "keenetic": {
                        "online": keenetic_online,
                        "model": self.router_model or "Роутер Keenetic",
                        "uptime": wan_uptime,
                        "down_speed_mbits": max(0.0, wan_speed_down),
                        "up_speed_mbits": max(0.0, wan_speed_up),
                        "clients": clients,
                        "clients_count": len(clients),
                        "repeaters": repeaters,
                        "cpu_load": cpu_load,
                        "ram_usage": ram_usage
                    },
                    "mihomo": {
                        "online": mihomo_online,
                        "mode": mihomo_mode,
                        "down_speed_mbits": self.latest_mihomo_traffic.get("down_speed_mbits", 0.0),
                        "up_speed_mbits": self.latest_mihomo_traffic.get("up_speed_mbits", 0.0),
                        "proxy_groups": proxy_groups,
                        "server_delays": delays
                    }
                })

            except Exception as e:
                self.log(f"Error in monitor loop: {e}", level=logging.WARNING)
                await self.emit_state({"connected": False})

            await asyncio.sleep(2.5)

    async def handle_command(self, action: str, data: any):
        """Маршрутизация и обработка входящих команд от GUI"""
        headers = self._get_headers()
        self.log(f"Received GUI command: {action}")

        if action == "get_settings_data":
            # Безопасно отправляем конфигурацию
            cfg = self.get_config()
            has_password = bool(self.get_secret("KEENETIC_PASSWORD", ""))
            has_secret = bool(self.get_secret("MIHOMO_SECRET", ""))
            
            await self.emit_event("settings_data", {
                "router_ip": cfg.get("router_ip", "192.168.1.1"),
                "router_login": cfg.get("router_login", "admin"),
                "mihomo_port": cfg.get("mihomo_port", 9097),
                "has_password": has_password,
                "has_secret": has_secret
            })

        elif action == "save_settings":
            # Валидация и верификация настроек перед сохранением
            ip = data.get("router_ip", "").strip()
            login = data.get("router_login", "").strip()
            port_raw = data.get("mihomo_port")
            pwd = data.get("router_password", "")
            sec = data.get("mihomo_secret", "")

            try:
                # 1. Валидация типов
                if not ip:
                    raise Exception("IP-адрес роутера не может быть пустым.")
                if not login:
                    raise Exception("Имя пользователя не может быть пустым.")
                
                try:
                    port = int(port_raw)
                    if not (1 <= port <= 65535): raise ValueError()
                except ValueError:
                    raise Exception("Порт Mihomo должен быть целым числом от 1 до 65535.")

                # 2. Подстановка существующих секретов при их маскировании
                final_pwd = self.get_secret("KEENETIC_PASSWORD", "") if pwd == "******" else pwd
                final_sec = self.get_secret("MIHOMO_SECRET", "") if sec == "******" else sec

                # 3. Асинхронный сухой запуск (dry-run) для проверки связи
                await self._test_keenetic_connection(ip, login, final_pwd)
                await self._test_mihomo_connection(ip, port, final_sec)

                # 4. Если всё успешно, сохраняем настройки
                self.save_config({
                    "router_ip": ip,
                    "router_login": login,
                    "mihomo_port": port
                })
                
                self.set_secret("KEENETIC_PASSWORD", final_pwd)
                self.set_secret("MIHOMO_SECRET", final_sec)
                
                # Обновляем локальные ссылки
                self.router_ip = ip
                self.mihomo_api_url = f"http://{ip}:{port}"
                self.router_model = ""

                # Отправляем уведомление об успешной валидации
                await self.emit_event("settings_validation_result", {"success": True})
                self.log("Settings successfully verified and saved.")
                
                # Перезапускаем циклы для немедленного применения изменений
                if self._monitoring_task: self._monitoring_task.cancel()
                if self._traffic_listener_task: self._traffic_listener_task.cancel()
                self._monitoring_task = self.create_task(self._monitoring_loop())
                self._traffic_listener_task = self.create_task(self._mihomo_traffic_listener())

            except Exception as e:
                self.log(f"Settings verification failed: {e}", level=logging.WARNING)
                await self.emit_event("settings_validation_result", {"success": False, "message": str(e)})

        elif action == "change_mode":
            # Переключение режима работы (Global, Rule, Direct)
            target_mode = data.get("mode", "rule").lower()
            try:
                async with self.session.patch(
                    f"{self.mihomo_api_url}/configs",
                    json={"mode": target_mode},
                    headers=headers,
                    timeout=3.0
                ) as resp:
                    if resp.status == 204:
                        self.log(f"Mihomo mode changed to: {target_mode}")
            except Exception as e:
                self.log(f"Failed to change Mihomo mode: {e}", level=logging.WARNING)

        elif action == "select_proxy":
            # Переключение прокси в группе
            group = data.get("group")
            server = data.get("server")
            try:
                async with self.session.put(
                    f"{self.mihomo_api_url}/proxies/{group}",
                    json={"name": server},
                    headers=headers,
                    timeout=3.0
                ) as resp:
                    if resp.status == 204:
                        self.log(f"Switched group [{group}] to server [{server}]")
            except Exception as e:
                self.log(f"Failed to switch proxy: {e}", level=logging.WARNING)

        elif action == "test_latency":
            # Запуск замера пинга
            group = data.get("group")
            try:
                async with self.session.post(
                    f"{self.mihomo_api_url}/proxies/{group}/delay",
                    params={"url": "http://www.gstatic.com/generate_204", "timeout": "5000"},
                    headers=headers,
                    timeout=5.0
                ) as resp:
                    self.log(f"Latency test triggered for group [{group}]")
            except Exception as e:
                self.log(f"Failed to trigger latency test: {e}", level=logging.WARNING)

        elif action == "reboot":
            # Удалённая перезагрузка роутера Keenetic
            if await self._authenticate_keenetic():
                try:
                    k_headers = self._get_keenetic_headers()
                    await self.session.post(f"http://{self.router_ip}/rci/system/reboot", headers=k_headers, timeout=3.0)
                    self.log("Reboot command successfully sent to Keenetic.")
                except Exception as e:
                    self.log(f"Failed to send reboot command: {e}", level=logging.WARNING)

        elif action == "toggle_guest_wifi":
            # Переключение гостевого Wi-Fi
            enable = data.get("enable", False)
            state_str = "up" if enable else "down"
            if await self._authenticate_keenetic():
                try:
                    k_headers = self._get_keenetic_headers()
                    await self.session.post(f"http://{self.router_ip}/rci/interface/WifiMaster0/AccessPoint1/{state_str}", headers=k_headers, timeout=3.0)
                    self.log(f"Guest Wi-Fi toggled to {state_str}")
                except Exception as e:
                    self.log(f"Failed to toggle Guest Wi-Fi: {e}", level=logging.WARNING)
