import { store } from './modules/store.js';
import { initSocketHandlers, socket } from './modules/socket.js';
import { registerAuthHandlers } from './modules/auth.js';
import { initNavigation, applyThemeColor, showToast } from './modules/ui.js';
import { switchLanguage, translations, applyTranslations, t } from './modules/i18n.js';
import { loadPlugins, initPluginHandlers } from './modules/plugins.js';
import { secureFetch } from './modules/api.js';

async function init() {
    console.log("Initializing MonitHome...");

    // 1. Initial UI Setup
    initNavigation();

    // 2. Load Config & i18n
    try {
        const res = await secureFetch('/api/config');
        const config = await res.json();

        // Update Store (triggers reactive updates in components like monit-settings-form)
        store.update({ config });

        // Load language
        await switchLanguage(config.language || 'ru');

        // Apply theme
        if (config.theme_color) applyThemeColor(config.theme_color);

    } catch (err) {
        console.error("Failed to load initial config", err);
    }

    // 3. Initialize Socket & Handlers
    initSocketHandlers();
    registerAuthHandlers(socket);
    initPluginHandlers();

    // 4. Initial Content Load
    loadPlugins();

    console.log("Initialization complete.");
}

// Global scope exposure for legacy/inline JS if needed (optional)
window.monit = { socket, t, secureFetch };

document.addEventListener('DOMContentLoaded', init);
