import { store } from '../modules/store.js';
import './monit-plugin-card.js';

class MonitPluginsList extends HTMLElement {
    connectedCallback() {
        this.unsubscribe = store.subscribe((state) => {
            this.render(state.plugins);
        });
    }

    disconnectedCallback() {
        if (this.unsubscribe) this.unsubscribe();
    }

    render(plugins) {
        if (!plugins || plugins.length === 0) {
            this.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding: 40px; color: var(--text-muted);">Loading plugins...</div>`;
            return;
        }

        this.innerHTML = '';
        const grid = document.createElement('div');
        grid.className = 'plugins-grid';
        
        plugins.forEach(p => {
            const card = document.createElement('monit-plugin-card');
            card.plugin = p;
            grid.appendChild(card);
        });
        
        this.appendChild(grid);
    }
}

customElements.define('monit-plugins-list', MonitPluginsList);
