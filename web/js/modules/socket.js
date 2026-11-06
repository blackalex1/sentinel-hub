import { getAuthToken } from './api.js';
import { applyThemeColor, showToast } from './ui.js';
import { t } from './i18n.js';
import { store } from './store.js';

export const socket = io(window.location.origin, {
    auth: {
        token: getAuthToken()
    }
});

export function initSocketHandlers() {
    socket.on('connect', () => {
        store.update({ connection: 'connected' });
    });

    socket.on('disconnect', () => {
        store.update({ connection: 'disconnected' });
    });

    socket.on('ui_config', (data) => {
        if (data.theme_color) applyThemeColor(data.theme_color);
        store.update({ config: { ...store.state.config, ...data } });
        // Dispatch custom event for plugins to reload
        window.dispatchEvent(new CustomEvent('monit:plugins-reload'));
    });

    socket.on('theme_update', (data) => {
        if (data.theme_color) applyThemeColor(data.theme_color);
        store.update({ config: { ...store.state.config, theme_color: data.theme_color } });
    });
    
    socket.on('language_changed', (data) => {
        store.update({ config: { ...store.state.config, language: data.language } });
        import('./i18n.js').then(m => m.switchLanguage(data.language));
    });

    socket.on('server_log', (payload) => {
        const msg = payload.message || '';
        let level = 'info';
        if (msg.includes('[WARNING]')) level = 'warning';
        else if (msg.includes('[ERROR]')) level = 'error';

        const logs = [...store.state.logs, { message: msg, level: level }];
        if (logs.length > 200) logs.shift();
        store.update({ logs });
    });

    socket.on('stats_json', (payload) => {
        const stats = payload.stats;
        if (stats.system_stats) {
            const s = stats.system_stats;
            store.update({
                stats: {
                    cpu: s.cpu !== undefined ? Math.round(s.cpu) : 0,
                    ram: s.ram_percent !== undefined ? Math.round(s.ram_percent) : 0,
                    temp: s.cpu_temp !== undefined ? Math.round(s.cpu_temp) : 0
                }
            });
        }
    });

    socket.on('connected_devices', (devices) => {
        store.update({ devices });
        window.dispatchEvent(new CustomEvent('monit:devices-update', { detail: devices }));
    });
}

function updateConnectionStatus(key, fallback) {
    const statusText = document.getElementById('connection-status');
    if (statusText) {
        statusText.textContent = t(key, fallback);
        statusText.setAttribute('data-i18n', key);
    }
}

function updateValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}
