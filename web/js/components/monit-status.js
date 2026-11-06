import { store } from '../modules/store.js';
import { t } from '../modules/i18n.js';

class MonitStatus extends HTMLElement {
    connectedCallback() {
        this.render();
        this.unsubscribe = store.subscribe((state) => {
            const dot = this.querySelector('.dot');
            const text = this.querySelector('.status-text');
            const status = state.connection;

            if (dot) {
                dot.className = `dot ${status === 'connected' ? 'connected' : ''}`;
            }

            if (text) {
                const key = status === 'connected' ? 'status_connected' : 'status_disconnected';
                text.textContent = t(key, status);
                text.setAttribute('data-i18n', key);
            }
        });
    }

    disconnectedCallback() {
        if (this.unsubscribe) this.unsubscribe();
    }

    render() {
        this.innerHTML = `
            <div class="status-indicator">
                <span class="dot"></span>
                <span class="status-text" data-i18n="status_connecting">Connecting...</span>
            </div>
        `;
    }
}

customElements.define('monit-status', MonitStatus);
