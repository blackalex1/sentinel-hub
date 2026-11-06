import { store } from '../modules/store.js';

class MonitStat extends HTMLElement {
    constructor() {
        super();
        this.key = this.getAttribute('key');
        this.unit = this.getAttribute('unit') || '';
    }

    connectedCallback() {
        this.render();
        // Подписываемся на изменения в Store
        this.unsubscribe = store.subscribe((state) => {
            if (this._lastLang !== state.config.language) {
                this._lastLang = state.config.language;
                this.render();
            }
            const val = state.stats[this.key];
            const valueEl = this.querySelector('.val');
            if (valueEl) {
                valueEl.textContent = `${Math.round(val)}${this.unit}`;
            }
        });
    }

    disconnectedCallback() {
        if (this.unsubscribe) this.unsubscribe();
    }

    render() {
        const label = this.getAttribute('label') || this.key.toUpperCase();
        this.innerHTML = `
            <div class="stat-chip">
                ${label}: <span class="val">--${this.unit}</span>
            </div>
        `;
    }
}

customElements.define('monit-stat', MonitStat);
