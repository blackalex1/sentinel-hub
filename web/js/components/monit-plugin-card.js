import { store } from '../modules/store.js';
import { t } from '../modules/i18n.js';
import { togglePlugin, requestPluginElevation, showPluginInfo, editPluginConfig, requestYandexQR } from '../modules/plugins.js';

class MonitPluginCard extends HTMLElement {
    set plugin(data) {
        this._data = data;
        this.render();
    }

    render() {
        const p = this._data;
        if (!p) return;

        const name = t(`plugin_name_${p.id}`, p.name);
        const desc = t(`plugin_desc_${p.id}`, p.description || 'No description available.');
        const runningStr = t('plugin_running', 'Running');
        const stoppedStr = t('plugin_stopped', 'Stopped');
        const loginStr = t('btn_yandex_login', 'Login with QR');

        this.className = 'plugin-card glass-panel';
        this.innerHTML = `
            <div class="plugin-header">
                <div class="plugin-info-left">
                    <h3 class="plugin-title">${name}</h3>
                    <p class="plugin-desc">${desc}</p>
                </div>
                <label class="switch">
                    <input type="checkbox" class="plugin-toggle" ${p.active ? 'checked' : ''}>
                    <span class="slider"></span>
                </label>
            </div>
            <div class="plugin-actions">
                <span style="font-size: 13px; color: ${p.active ? 'var(--success)' : 'var(--text-muted)'}">
                    ${p.active ? '● ' + runningStr : '○ ' + stoppedStr}
                </span>
                <div style="display:flex; gap: 8px; align-items: center;">
                    ${p.elevation_active ? `
                        <button class="plugin-btn elevation-active-btn" title="${t('status_elevated', 'Admin Rights Active')}" style="background: var(--success); border-color: rgba(16, 185, 129, 0.4); cursor: default;">🛡️</button>
                    ` : (p.needs_elevation ? `
                        <button class="plugin-btn elevation-request-btn" title="${t('btn_elevate', 'Request Admin Rights')}" style="background: var(--danger); border-color: rgba(239, 68, 68, 0.4); animation: pulse-red 2s infinite;">🛡️</button>
                    ` : '')}
                    <button class="plugin-btn info-btn" title="${t('btn_info', 'Info')}">ℹ️</button>
                    ${p.has_settings ? `<button class="plugin-btn settings-btn" title="${t('btn_settings', 'Settings')}">⚙️</button>` : ''}
                    ${p.id === 'yandex_station' && p.active ? `<button class="plugin-btn yandex-qr-btn">${loginStr}</button>` : ''}
                </div>
            </div>
        `;

        // Handlers
        this.querySelector('.plugin-toggle').onchange = (e) => togglePlugin(p.id, e.target.checked);
        const elevBtn = this.querySelector('.elevation-request-btn');
        if (elevBtn) elevBtn.onclick = () => requestPluginElevation(p.id);
        this.querySelector('.info-btn').onclick = () => showPluginInfo(p.id);
        const settingsBtn = this.querySelector('.settings-btn');
        if (settingsBtn) settingsBtn.onclick = () => editPluginConfig(p.id);
        const yandexBtn = this.querySelector('.yandex-qr-btn');
        if (yandexBtn) yandexBtn.onclick = () => requestYandexQR();
    }
}

customElements.define('monit-plugin-card', MonitPluginCard);
