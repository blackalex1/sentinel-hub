import { store } from '../modules/store.js';
import { t } from '../modules/i18n.js';
import { secureFetch } from '../modules/api.js';

class MonitSettingsForm extends HTMLElement {
    connectedCallback() {
        this.render();
        this.unsubscribe = store.subscribe((state) => {
            this.sync(state.config);
        });

        this.querySelector('form').onsubmit = (e) => this.handleSubmit(e);
        
        // Immediate save for autostart
        const autostart = this.querySelector('#server-autostart');
        if (autostart) {
            autostart.onchange = (e) => {
                this.saveField('autostart', e.target.checked);
            };
        }

        // Живое обновление HEX при выборе цвета в пикере
        const picker = this.querySelector('#server-theme-picker');
        const hex = this.querySelector('#server-theme-hex');
        if (picker && hex) {
            picker.oninput = (e) => {
                const color = e.target.value.toUpperCase();
                hex.value = '0xFF' + color.substring(1);
            };
        }
    }

    disconnectedCallback() {
        if (this.unsubscribe) this.unsubscribe();
    }

    sync(config) {
        if (!config) return;
        const hostname = this.querySelector('#server-hostname');
        const lang = this.querySelector('#server-language');
        const autostart = this.querySelector('#server-autostart');
        const hex = this.querySelector('#server-theme-hex');
        const picker = this.querySelector('#server-theme-picker');

        // Only update if not focused and value changed to avoid UI glitches during stats updates
        if (hostname && document.activeElement !== hostname && hostname.value !== (config.hostname || '')) {
            hostname.value = config.hostname || '';
        }
        if (lang && document.activeElement !== lang && lang.value !== (config.language || 'ru')) {
            lang.value = config.language || 'ru';
        }
        if (autostart && autostart.checked !== (config.autostart || false)) {
            autostart.checked = config.autostart || false;
        }
        if (hex && document.activeElement !== hex && hex.value !== (config.theme_color || '0xFF22C55E')) {
            hex.value = config.theme_color || '0xFF22C55E';
        }
        
        if (picker && config.theme_color) {
            const c = config.theme_color;
            const hexVal = c.startsWith('0xFF') ? '#' + c.substring(4) : c.replace('0x', '#');
            if (picker.value !== hexVal) picker.value = hexVal;
        }
    }

    async saveField(key, value) {
        try {
            await secureFetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ [key]: value })
            });
        } catch (err) {
            console.error(`Failed to save ${key}`, err);
        }
    }

    async handleSubmit(e) {
        e.preventDefault();
        const btn = this.querySelector('#save-config-btn');
        const originalText = btn.textContent;

        btn.textContent = t('btn_saving', 'Saving...');
        btn.disabled = true;

        const newConfig = {
            hostname: this.querySelector('#server-hostname').value,
            language: this.querySelector('#server-language').value,
            theme_color: this.querySelector('#server-theme-hex').value,
            autostart: this.querySelector('#server-autostart').checked
        };

        try {
            const res = await secureFetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newConfig)
            });

            if (res.ok) {
                btn.textContent = t('btn_saved', 'Saved!');
                btn.style.background = 'var(--success)';
                setTimeout(() => {
                    btn.textContent = originalText;
                    btn.style.background = 'var(--accent)';
                    btn.disabled = false;
                }, 2000);
            }
        } catch (err) {
            console.error("Failed to save config", err);
            btn.textContent = 'Error!';
            btn.style.background = 'var(--danger)';
            setTimeout(() => {
                btn.textContent = originalText;
                btn.style.background = 'var(--accent)';
                btn.disabled = false;
            }, 2000);
        }
    }

    render() {
        this.innerHTML = `
            <header class="section-header">
                <h2 data-i18n="settings_title">${t('settings_title', 'Global Settings')}</h2>
                <p data-i18n="settings_desc">${t('settings_desc', 'Configure the core MonitHome server.')}</p>
            </header>
            <div class="glass-panel p-4">
                <form id="global-settings-form">
                    <div class="form-group">
                        <label for="server-hostname" data-i18n="server_name">${t('server_name', 'Server Name')}</label>
                        <input type="text" id="server-hostname" class="form-input" placeholder="MonitHome PC">
                    </div>

                    <div class="form-group">
                        <label for="server-language" data-i18n="interface_lang">${t('interface_lang', 'Interface Language')}</label>
                        <select id="server-language" class="form-input">
                            <option value="ru">Russian (RU)</option>
                            <option value="en">English (EN)</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label for="server-theme-color" data-i18n="accent_color">${t('accent_color', 'Accent Color')}</label>
                        <div class="color-picker-container">
                            <input type="color" id="server-theme-picker" class="form-input color-picker">
                            <input type="text" id="server-theme-hex" class="form-input color-hex" placeholder="0xFF22C55E">
                        </div>
                    </div>

                    <div class="form-group" style="display: flex; align-items: center; justify-content: space-between; background: rgba(255,255,255,0.03); padding: 15px; border-radius: 12px; border: 1px solid var(--border-color);">
                        <div>
                            <label style="margin-bottom: 4px; color: white;" data-i18n="autostart_label">${t('autostart_label', 'Autostart with Windows')}</label>
                            <p style="font-size: 12px; color: var(--text-muted);" data-i18n="autostart_desc">${t('autostart_desc', 'Start MonitHome automatically when you log in.')}</p>
                        </div>
                        <label class="switch">
                            <input type="checkbox" id="server-autostart">
                            <span class="slider"></span>
                        </label>
                    </div>

                    <div class="form-actions mt-4">
                        <button type="submit" class="btn btn-primary" id="save-config-btn" data-i18n="save_config">${t('save_config', 'Save Configuration')}</button>
                    </div>
                </form>
            </div>
        `;
    }
}

customElements.define('monit-settings-form', MonitSettingsForm);
