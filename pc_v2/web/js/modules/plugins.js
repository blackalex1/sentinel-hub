import { socket } from './socket.js';
import { secureFetch } from './api.js';
import { t } from './i18n.js';
import { showModal, closeModal } from './ui.js';
import { customHandlers } from './plugin_custom.js';

import { store } from './store.js';

export async function loadPlugins() {
    try {
        const response = await secureFetch('/api/plugins');
        const data = await response.json();

        if (data && data.plugins) {
            store.update({ plugins: data.plugins });
        } else {
            console.warn("No plugins data received or unauthorized");
            store.update({ plugins: [] });
        }
    } catch (err) {
        console.error("Failed to load plugins", err);
    }
}


export async function togglePlugin(pluginId, isActive) {
    try {
        const res = await secureFetch('/api/plugins/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plugin_id: pluginId, active: isActive })
        });
        if (res.ok) {
            setTimeout(loadPlugins, 500);
        }
    } catch (err) {
        console.error("Failed to toggle plugin", err);
    }
}

export function requestPluginElevation(pluginId) {
    socket.emit('plugin_command', {
        plugin_id: pluginId,
        action: 'request_elevation',
        data: {}
    });
}

export async function showPluginInfo(pluginId) {
    try {
        const res = await secureFetch(`/api/plugins/${pluginId}/config`);
        const config = await res.json();

        const name = t(`plugin_name_${pluginId}`, config.name || pluginId);
        const desc = t(`plugin_desc_${pluginId}`, config.description || 'No description available.');
        
        showModal({
            title: name,
            content: `
                <div style="text-align: left; width: 100%; font-size: 14px; color: var(--text-muted);">
                    <p><strong>ID:</strong> ${pluginId}</p>
                    <p><strong>${t('label_version', 'Version')}:</strong> ${config.version || 'Unknown'}</p>
                    <p><strong>${t('label_author', 'Author')}:</strong> ${config.author_name || 'Unknown'}</p>
                    <p style="margin-top: 10px;">${desc}</p>
                </div>
            `
        });
    } catch (err) { console.error(err); }
}

export async function editPluginConfig(pluginId) {
    const activePlugins = store.state.plugins || [];
    const pluginData = activePlugins.find(p => p.id === pluginId);
    const isActive = pluginData ? pluginData.active : false;
    const customWizards = ['yandex_station', 'pc_disks', 'system_stats', 'keenetic_mihomo'];

    if (customWizards.includes(pluginId) && !isActive) {
        showModal({
            title: t(`plugin_name_${pluginId}`, pluginId),
            content: `
                <div style="text-align: center; padding: 25px; color: var(--text-muted); font-size: 14px; line-height: 1.5;">
                    <p style="font-size: 28px; margin-bottom: 12px;">⚠️</p>
                    <p>${t('error_enable_plugin_first', 'Пожалуйста, включите плагин перед изменением настроек.')}</p>
                </div>
            `
        });
        return;
    }

    if (pluginId === 'yandex_station') {
        showModal({ title: t('yandex_settings_title', "Яндекс Станция"), content: `<div class="loading-spinner"></div>` });
        socket.emit('plugin_command', { plugin_id: 'yandex_station', action: 'get_wizard_data', data: {} });
        return;
    }

    try {
        const res = await secureFetch(`/api/plugins/${pluginId}/config`);
        const config = await res.json();
        const pluginName = t(`plugin_name_${pluginId}`, config.name || pluginId);

        showModal({
            title: `${t('label_settings', 'Settings')}: ${pluginName}`,
            content: `<div class="settings-content"></div>`
        });

        if (customHandlers[pluginId]) {
            customHandlers[pluginId].render(config);
        } else {
            // Fallback to JSON editor
            const content = document.querySelector('.settings-content');
            content.innerHTML = `
                <div id="json-error" style="color: #ef4444; font-size: 12px; margin-bottom: 8px; height: 18px; visibility: hidden;">Invalid JSON</div>
                <textarea id="config-editor" style="width:100%; height: 300px; background: #020617; color: #a5b4fc; font-family: monospace; padding: 10px; border-radius: 8px; border: 1px solid var(--border-color);"></textarea>
                <button class="plugin-btn" style="width: 100%; background: var(--accent); margin-top: 10px;" id="save-plugin-config-btn">${t('btn_save_changes', 'Save Changes')}</button>
            `;
            const editor = content.querySelector('#config-editor');
            const saveBtn = content.querySelector('#save-plugin-config-btn');
            const errorDiv = content.querySelector('#json-error');

            editor.value = JSON.stringify(config, null, 2);

            const validate = () => {
                try {
                    JSON.parse(editor.value);
                    errorDiv.style.visibility = 'hidden';
                    saveBtn.disabled = false;
                    saveBtn.style.opacity = '1';
                } catch (e) {
                    errorDiv.style.visibility = 'visible';
                    errorDiv.textContent = `Error: ${e.message}`;
                    saveBtn.disabled = true;
                    saveBtn.style.opacity = '0.5';
                }
            };

            editor.oninput = validate;
            saveBtn.onclick = () => savePluginConfig(pluginId, editor.value);
        }
    } catch (err) { console.error(err); }
}

async function savePluginConfig(pluginId, jsonString) {
    try {
        const newConfig = JSON.parse(jsonString);
        const res = await secureFetch(`/api/plugins/${pluginId}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config_data: newConfig })
        });
        if (res.ok) {
            closeModal();
            loadPlugins();
        }
    } catch (err) {
        alert("Invalid JSON format!");
    }
}

export function requestYandexQR() {
    showModal({
        title: t('yandex_auth_title', "Yandex Station Auth"),
        content: `<p>${t('requesting_qr', 'Requesting QR Code...')}</p>`
    });
    socket.emit('plugin_command', { plugin_id: 'yandex_station', action: 'start_qr_login', data: {} });
}

export function initPluginHandlers() {
    socket.on('plugin_state_changed', (payload) => {
        if (!payload || !payload.plugin_id) return;
        const plugins = store.state.plugins || [];
        const existing = plugins.find(p => p.id === payload.plugin_id);
        if (existing) {
            const needs_elevation = payload.state?.needs_elevation ?? existing.needs_elevation;
            const elevation_active = payload.state?.elevation_active ?? existing.elevation_active;
            if (existing.needs_elevation !== needs_elevation || existing.elevation_active !== elevation_active) {
                loadPlugins();
            }
        } else {
            loadPlugins();
        }
    });
    
    // Global plugin event routing
    socket.onAny((event, payload) => {
        if (event.startsWith('plugin_event:')) {
            const pId = event.split(':')[1];
            if (customHandlers[pId] && customHandlers[pId].onEvent) {
                customHandlers[pId].onEvent(payload);
            }
        }
    });

    socket.on('plugin_event:yandex_station', (payload) => {
        if (payload.event === 'show_qr') {
            const data = payload.data;
            let html = `<p style="color: var(--accent); font-weight: 500;">${data.status || 'Waiting...'}</p>`;
            if (data.qr_url) {
                html += `<img src="${data.qr_url}" alt="QR Code" style="max-width: 250px; border-radius: 12px; margin: 15px 0;">`;
                html += `<p style="font-size: 13px; color: var(--text-muted);">${data.instructions || 'Scan with Yandex App'}</p>`;
            }
            showModal({ title: t('yandex_auth_title', "Yandex Station Auth"), content: html });
        }
    });

    window.addEventListener('monit:plugins-reload', () => loadPlugins());
}
