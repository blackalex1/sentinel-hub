import { store } from '../modules/store.js';
import { t } from '../modules/i18n.js';

class MonitLogPanel extends HTMLElement {
    constructor() {
        super();
        this.currentLogLevel = 'all';
    }

    connectedCallback() {
        this.render();
        this.unsubscribe = store.subscribe((state) => {
            this.updateLogs(state.logs);
        });

        // Слушаем переключение фильтров
        this.querySelectorAll('.filter-btn').forEach(btn => {
            btn.onclick = (e) => {
                this.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.currentLogLevel = e.target.getAttribute('data-level');
                this.updateLogs(store.state.logs);
            };
        });
    }

    disconnectedCallback() {
        if (this.unsubscribe) this.unsubscribe();
    }

    updateLogs(logs) {
        const output = this.querySelector('#log-output');
        const container = this.querySelector('.logs-container');
        if (!output || !container) return;

        // Проверяем, находится ли пользователь в самом низу (с запасом 50px)
        const isAtBottom = (container.scrollHeight - container.clientHeight - container.scrollTop) < 50;

        // Фильтруем новые логи по текущему уровню
        const filteredLogs = logs.filter(log => this.currentLogLevel === 'all' || this.currentLogLevel === log.level);
        const children = output.children;

        // Если это просто добавление новых логов в конец списка
        if (children.length > 0 && filteredLogs.length >= children.length && 
            filteredLogs[children.length - 1].message === children[children.length - 1].textContent) {
            
            const fragment = document.createDocumentFragment();
            for (let i = children.length; i < filteredLogs.length; i++) {
                const div = document.createElement('div');
                div.className = `log-line log-${filteredLogs[i].level}`;
                div.textContent = filteredLogs[i].message;
                fragment.appendChild(div);
            }
            output.appendChild(fragment);

            // Удаляем старые строки с начала, чтобы в DOM оставалось не больше 200 строк
            while (children.length > 200) {
                output.removeChild(output.firstChild);
            }
        } else {
            // При первой загрузке или смене фильтра полностью перестраиваем DOM
            output.innerHTML = '';
            const fragment = document.createDocumentFragment();
            filteredLogs.forEach(log => {
                const div = document.createElement('div');
                div.className = `log-line log-${log.level}`;
                div.textContent = log.message;
                fragment.appendChild(div);
            });
            output.appendChild(fragment);
        }
        
        // Автопрокрутка срабатывает только если пользователь до этого смотрел низ
        if (isAtBottom) {
            container.scrollTop = container.scrollHeight;
        }
    }

    render() {
        this.innerHTML = `
            <header class="section-header">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px;">
                    <div>
                        <h2 data-i18n="nav_logs">${t('nav_logs', 'Server Logs')}</h2>
                        <p data-i18n="logs_desc">${t('logs_desc', 'Real-time system and plugin activity.')}</p>
                    </div>
                    <div class="log-filters glass-panel" style="display: flex; gap: 5px; padding: 5px; border-radius: 12px;">
                        <button class="filter-btn active" data-level="all" data-i18n="log_filter_all">${t('log_filter_all', 'All')}</button>
                        <button class="filter-btn" data-level="info" data-i18n="log_filter_info">${t('log_filter_info', 'Info')}</button>
                        <button class="filter-btn" data-level="warning" data-i18n="log_filter_warning">${t('log_filter_warning', 'Warning')}</button>
                        <button class="filter-btn" data-level="error" data-i18n="log_filter_error">${t('log_filter_error', 'Error')}</button>
                    </div>
                </div>
            </header>
            <div class="glass-panel logs-container">
                <pre id="log-output"></pre>
            </div>
        `;
    }
}

customElements.define('monit-log-panel', MonitLogPanel);
