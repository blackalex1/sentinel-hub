<div align="center">

# 🖥️ Sentinel Hub

### Сервер телеметрии ПК, драйверов и хаб умного дома для экосистемы Sentinel

[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-0078D6.svg?style=flat-square&logo=windows)](https://microsoft.com/windows)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?style=flat-square&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688.svg?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6%20%2F%20Chromium-41CD52.svg?style=flat-square&logo=qt)](https://www.qt.io/)
[![Ecosystem: Sentinel](https://img.shields.io/badge/Ecosystem-Sentinel-8a2be2.svg?style=flat-square)](https://github.com/blackalex1)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

<p align="center">
  Центральный серверный компонент экосистемы <b>Sentinel</b> для персонального компьютера. Отвечает за сбор телеметрии железа, управление питанием и звуком, трансляцию видеопотока веб-камер и сетевую интеграцию с мобильной консолью <b>Sentinel Deck</b>.
</p>

</div>

---

## 🌟 Основные модули и плагины

* **⚡ Телеметрия ПК (System Stats):**
  * Сбор в реальном времени частот, температур и загрузки CPU и GPU (интеграция с LibreHardwareMonitor и MSI Afterburner).
  * Мониторинг использования ОЗУ и состояния накопителей (SSD/HDD).
* **🎵 Медиа-шлюз (Media Hub):**
  * **Sentinel Music**: прямое подключение к Sentinel Connect (WSS) с синхронизацией треков и караоке-текстов.
  * **Яндекс.Станции**: локальное управление колонками через Glagol API по Wi-Fi.
  * **PC Media**: перехват и управление громкостью и плеерами Windows (GSMTC).
* **🌐 Сетевой шлюз (Keenetic & Mihomo):**
  * Опрос статистики сетевого трафика с роутеров Keenetic через RCI API.
  * Управление правилами и прокси-нодами Mihomo (Clash Meta).
* **📹 Драйвер виртуальной камеры (Virtual Camera):**
  * Интеграция UnityCapture для захвата видеопотока с камеры Android (Sentinel Deck) через RTSP/ADB с минимальной задержкой.
* **🚀 Панель макросов (App Launcher):**
  * Удаленный запуск программ, выполнение консольных команд, эмуляция клавиатурных сочетаний (hotkeys) и перевод ПК в режим сна / блокировки.
* **🔒 Безопасность и сопряжение:**
  * Защита локальных сокетов одноразовыми токенами сопряжения с экрана ПК.
  * Автообнаружение через Zeroconf (mDNS `_monithome._tcp.local.`).
  * Шифрование секретов в локальной БД (AES-256).

---

## 🏛 Архитектура

```mermaid
flowchart TD
    subgraph PC[" 🖥️ Рабочая станция Windows (Sentinel Hub) "]
        Core["Серверное ядро (FastAPI + Socket.IO)"]
        GUI["Интерфейс управления (PySide6 / WebEngine)"]
        Plugins["Система плагинов:<br/>• System Stats<br/>• Sentinel Music<br/>• Yandex Glagol<br/>• Keenetic / Mihomo<br/>• Virtual Camera"]
        Core <--> Plugins
        Core <--> GUI
    end

    subgraph Deck[" 🎮 Мобильная консоль (Sentinel Deck) "]
        Tablet["Android Планшет / Смартфон<br/>(Jetpack Compose Dashboard)"]
    end

    Core <== "mDNS Discovery + WebSocket (AES-256)" ==> Tablet
```

---

## 🚀 Быстрый запуск

### 1. Установка зависимостей
Требуется **Python 3.10+**.

```bash
git clone https://github.com/blackalex1/sentinel-hub.git
cd sentinel-hub

# Создание и активация виртуального окружения
python -m venv venv
.\venv\Scripts\activate

# Установка зависимостей
pip install -r requirements.txt
```

### 2. Запуск приложения

```bash
# Запуск с графическим интерфейсом в трее
python pc_v2/pc_gui_app.py

# Или фоновый запуск только сервера
python pc_v2/main.py
```

### 3. Запуск тестов

```bash
pytest pc_v2/tests
```

---

<div align="center">
Часть экосистемы <b>Sentinel</b> • Разработано с ❤️
</div>
