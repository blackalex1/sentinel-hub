import { store } from '../modules/store.js';
import { t } from '../modules/i18n.js';
import { socket } from '../modules/socket.js';

class MonitDevicesList extends HTMLElement {
    connectedCallback() {
        this.unsubscribe = store.subscribe((state) => {
            this.render(state.devices);
        });
    }

    disconnectedCallback() {
        if (this.unsubscribe) this.unsubscribe();
    }

    render(devices) {
        if (!devices || devices.length === 0) {
            this.innerHTML = `
                <header class="section-header">
                    <h2 data-i18n="nav_devices">${t('nav_devices', 'Connected Devices')}</h2>
                    <p data-i18n="devices_desc">${t('devices_desc', 'List of all active sessions controlling your PC.')}</p>
                </header>
                <div class="devices-grid">
                    <p class="no-devices" data-i18n="no_devices_connected">${t('no_devices_connected', 'No external devices connected')}</p>
                </div>
            `;
            return;
        }

        this.innerHTML = `
            <header class="section-header">
                <h2 data-i18n="nav_devices">${t('nav_devices', 'Connected Devices')}</h2>
                <p data-i18n="devices_desc">${t('devices_desc', 'List of all active sessions controlling your PC.')}</p>
            </header>
            <div class="devices-grid"></div>
        `;

        const grid = this.querySelector('.devices-grid');
        devices.forEach(dev => {
            const card = document.createElement('div');
            card.className = 'device-card glass-panel';
            
            let icon = '🌐';
            if (dev.type === 'PC GUI') icon = '💻';
            else if (dev.type === 'Tablet') icon = '📱';

            card.innerHTML = `
                <div class="device-icon">${icon}</div>
                <div class="device-info">
                    <div class="device-name">${dev.type}</div>
                    <div class="device-detail">IP: ${dev.ip}</div>
                    <div class="device-ua" title="${dev.ua}">${dev.ua}</div>
                </div>
                <div class="device-status"><span class="dot connected"></span>Online</div>
                ${dev.type !== 'PC GUI' ? `<button class="plugin-btn danger kick-btn">Disconnect</button>` : ''}
            `;
            const kickBtn = card.querySelector('.kick-btn');
            if (kickBtn) {
                kickBtn.onclick = () => {
                    if (confirm(t('confirm_kick', "Disconnect this device?"))) {
                        socket.emit('kick_device', { sid: dev.sid });
                    }
                };
            }
            grid.appendChild(card);
        });
    }
}

customElements.define('monit-devices-list', MonitDevicesList);
