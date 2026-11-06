/**
 * Модуль Store для реактивного управления состоянием MonitHome.
 * Реализован через Proxy для автоматического отслеживания изменений.
 */

class Store {
    constructor(initialState = {}) {
        this.listeners = new Set();
        this.state = new Proxy(initialState, {
            set: (target, key, value) => {
                target[key] = value;
                this.notify();
                return true;
            }
        });
    }

    /** Подписаться на изменения состояния */
    subscribe(listener) {
        this.listeners.add(listener);
        // Сразу вызываем один раз, чтобы синхронизировать начальное состояние
        listener(this.state);
        return () => this.listeners.delete(listener);
    }

    /** Уведомить всех подписчиков */
    notify() {
        this.listeners.forEach(listener => listener(this.state));
    }

    /** Обновить состояние (аналог dispatch/commit) */
    update(patch) {
        Object.assign(this.state, patch);
    }
}

// Глобальное начальное состояние
export const store = new Store({
    stats: {
        cpu: 0,
        ram: 0,
        temp: 0
    },
    config: {
        hostname: 'MonitHome PC',
        language: 'ru',
        theme_color: '0xFF22C55E'
    },
    plugins: [],
    devices: [],
    logs: [],
    connection: 'connecting'
});
