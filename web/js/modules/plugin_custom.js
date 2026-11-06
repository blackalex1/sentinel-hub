import { socket } from './socket.js';
import { secureFetch } from './api.js';
import { t } from './i18n.js';
import { showModal, closeModal, showToast } from './ui.js';

const modalContent = document.getElementById('modal-content');

export const customHandlers = {
    'system_stats': {
        render: async (config) => {
            let html = `<div class="settings-list">`;
            for (const [key, enabled] of Object.entries(config.enabled_sensors)) {
                const label = t(`sensor_${key}`, key);
                html += `
                    <div class="settings-item glass-panel" style="display:flex; justify-content: space-between; padding: 12px; margin-bottom: 8px;">
                        <span>${label}</span>
                        <label class="switch">
                            <input type="checkbox" id="sensor-${key}" ${enabled ? 'checked' : ''}>
                            <span class="slider"></span>
                        </label>
                    </div>
                `;
            }
            html += `</div>
            <button class="plugin-btn" style="width: 100%; background: var(--accent); margin-top: 15px;" id="save-sensors-btn">${t('btn_save_changes', 'Save Changes')}</button>`;
            
            modalContent.innerHTML = html;
            modalContent.querySelector('#save-sensors-btn').onclick = () => {
                const sensors = {};
                modalContent.querySelectorAll('input[type="checkbox"]').forEach(sw => {
                    sensors[sw.id.replace('sensor-', '')] = sw.checked;
                });
                socket.emit('plugin_command', { plugin_id: 'system_stats', action: 'update_sensor_settings', data: sensors });
                closeModal();
            };
        }
    },
    'pc_disks': {
        render: (config) => {
            modalContent.innerHTML = `<div class="loading-spinner"></div>`;
            socket.emit('plugin_command', { plugin_id: 'pc_disks', action: 'get_disks_for_settings', data: {} });
        },
        onEvent: (payload) => {
            if (payload.event === 'disks_for_settings') {
                const { all_disks, monitored_disks, show_new_disks } = payload.data;
                let html = `<div class="settings-list">
                    <div class="settings-item glass-panel" style="display:flex; justify-content: space-between; padding: 12px; margin-bottom: 15px; border-bottom: 2px solid var(--accent);">
                        <span style="font-weight: bold;">${t('setting_show_new_disks', 'Show new disks')}</span>
                        <label class="switch">
                            <input type="checkbox" id="disk-show-new" ${show_new_disks ? 'checked' : ''}>
                            <span class="slider"></span>
                        </label>
                    </div>
                    <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 10px;">${t('setting_monitored_disks', 'Monitored Disks')}:</p>
                `;
                all_disks.forEach(disk => {
                    const isMonitored = monitored_disks.includes(disk.device);
                    html += `
                        <div class="settings-item glass-panel" style="display:flex; justify-content: space-between; padding: 10px; margin-bottom: 8px;">
                            <span>${disk.device} (${disk.label || 'Disk'})</span>
                            <label class="switch">
                                <input type="checkbox" class="disk-checkbox" data-device="${disk.device}" ${isMonitored ? 'checked' : ''}>
                                <span class="slider"></span>
                            </label>
                        </div>
                    `;
                });
                html += `</div><button class="plugin-btn" style="width: 100%; background: var(--accent); margin-top: 15px;" id="save-disks-btn">${t('btn_save_changes', 'Save Changes')}</button>`;
                modalContent.innerHTML = html;
                modalContent.querySelector('#save-disks-btn').onclick = () => {
                    const monitored = Array.from(modalContent.querySelectorAll('.disk-checkbox:checked')).map(cb => cb.getAttribute('data-device'));
                    socket.emit('plugin_command', {
                        plugin_id: 'pc_disks',
                        action: 'update_settings',
                        data: { monitored_disks: monitored, show_new_disks: modalContent.querySelector('#disk-show-new').checked }
                    });
                    closeModal();
                };
            }
        }
    },
    'app_launcher': {
        render: (config) => {
            renderAppLauncherUI(config);
        },
        onEvent: (payload) => {
            if (payload.event === 'config_updated') {
                secureFetch('/api/plugins/app_launcher/config').then(res => res.json()).then(renderAppLauncherUI);
            } else if (payload.event === 'file_selected') {
                const pathInput = document.getElementById('new-app-path');
                const nameInput = document.getElementById('new-app-name');
                const previewDiv = document.getElementById('new-app-icon-preview');
                if (pathInput) pathInput.value = payload.data.path;
                if (nameInput) nameInput.value = payload.data.label;
                if (previewDiv && payload.data.icon) {
                    previewDiv.innerHTML = `<img src="${payload.data.icon}" style="width: 100%; height: 100%; object-fit: contain; transform: scale(1.15);">`;
                    previewDiv.style.borderStyle = 'solid';
                    previewDiv.style.borderColor = 'var(--accent)';
                }
            }
        }
    },
    'yandex_station': {
        render: (config) => {
            modalContent.innerHTML = `<div class="loading-spinner"></div>`;
            socket.emit('plugin_command', { plugin_id: 'yandex_station', action: 'get_wizard_data', data: {} });
        },
        onEvent: (payload) => {
            if (payload.event === 'wizard_data') {
                const { devices, tablet_control, selected_device_ids } = payload.data;
                let html = `
                    <div class="yandex-settings">
                        <div class="settings-group glass-panel mb-4" style="padding: 15px;">
                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                <div>
                                    <h4 style="color: var(--accent); margin-bottom: 4px;">${t('label_tablet_control', 'Управление с планшета')}</h4>
                                    <p style="font-size: 12px; color: var(--text-muted);">${t('desc_tablet_control', 'Разрешить планшету управлять колонками напрямую')}</p>
                                </div>
                                <label class="switch">
                                    <input type="checkbox" id="yandex-tablet-control" ${tablet_control ? 'checked' : ''}>
                                    <span class="slider"></span>
                                </label>
                            </div>
                        </div>

                        <div class="settings-group mb-4">
                            <h4 style="color: var(--accent); margin-bottom: 10px;">${t('label_select_speakers', 'Выберите колонки')}</h4>
                            <div class="devices-selection-list" style="display: flex; flex-direction: column; gap: 8px;">
                                ${devices.map(d => `
                                    <div class="settings-item glass-panel" style="display:flex; justify-content: space-between; padding: 12px;">
                                        <span>${d.name}</span>
                                        <label class="switch">
                                            <input type="checkbox" class="yandex-device-checkbox" data-id="${d.id}" ${selected_device_ids.includes(d.id) ? 'checked' : ''}>
                                            <span class="slider"></span>
                                        </label>
                                    </div>
                                `).join('') || `<p style="color: var(--text-muted);">${t('no_devices_found', 'Колонки не найдены')}</p>`}
                            </div>
                        </div>

                        <div class="settings-group mb-4">
                            <button class="plugin-btn" style="width: 100%; border-color: #f59e0b; color: #f59e0b; background: rgba(245, 158, 11, 0.1);" id="yandex-qr-login-btn">
                                🔑 ${t('btn_qr_login', 'Войти через QR-код')}
                            </button>
                        </div>

                        <button class="plugin-btn" style="width: 100%; background: var(--accent); color: white;" id="yandex-save-btn">${t('btn_save_changes', 'Сохранить изменения')}</button>
                    </div>
                `;
                modalContent.innerHTML = html;

                modalContent.querySelector('#yandex-qr-login-btn').onclick = () => {
                    socket.emit('plugin_command', { plugin_id: 'yandex_station', action: 'start_qr_login', data: {} });
                    modalContent.innerHTML = `<div class="loading-spinner"></div><p style="text-align:center; margin-top:10px;">${t('getting_qr', 'Получение QR-кода...')}</p>`;
                };

                modalContent.querySelector('#yandex-save-btn').onclick = () => {
                    const selected = Array.from(modalContent.querySelectorAll('.yandex-device-checkbox:checked')).map(cb => cb.getAttribute('data-id'));
                    const tablet = modalContent.querySelector('#yandex-tablet-control').checked;
                    socket.emit('plugin_command', {
                        plugin_id: 'yandex_station',
                        action: 'handle_wizard',
                        data: { selected_device_ids: selected, tablet_control: tablet }
                    });
                    closeModal();
                };
            } else if (payload.event === 'show_qr') {
                const { qr_url, status, instructions } = payload.data;
                modalContent.innerHTML = `
                    <div class="qr-container" style="text-align: center; padding: 20px;">
                        <h3 style="margin-bottom: 15px; color: var(--accent);">${status}</h3>
                        <div style="background: white; padding: 15px; border-radius: 15px; display: inline-block; margin-bottom: 15px;">
                            <img src="${qr_url}" style="width: 256px; height: 256px;">
                        </div>
                        <p style="color: var(--text-muted);">${instructions}</p>
                        <button class="plugin-btn mt-4" style="width: 100%;" id="yandex-back-to-settings">${t('btn_back', 'Назад')}</button>
                    </div>
                `;
                modalContent.querySelector('#yandex-back-to-settings').onclick = () => {
                    customHandlers['yandex_station'].render();
                };
            }
        }
    },
    'keenetic_mihomo': {
        render: (config) => {
            modalContent.innerHTML = `<div class="loading-spinner"></div>`;
            socket.emit('plugin_command', { plugin_id: 'keenetic_mihomo', action: 'get_settings_data', data: {} });
        },
        onEvent: (payload) => {
            if (payload.event === 'settings_data') {
                const { router_ip, router_login, mihomo_port, has_password, has_secret } = payload.data;
                const ipLabel = t('label_router_ip', 'IP-адрес роутера');
                const loginLabel = t('label_router_login', 'Логин роутера');
                const pwdLabel = t('label_router_pwd', 'Пароль роутера');
                const portLabel = t('label_mihomo_port', 'Порт API Mihomo');
                const secLabel = t('label_mihomo_secret', 'Секретный токен Mihomo');
                const descLabel = t('desc_router_settings', 'Настройки подключения к Keenetic и Mihomo API. Все пароли и секреты надёжно шифруются.');

                let html = `
                    <div class="keenetic-settings" style="text-align: left;">
                        <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 20px; line-height: 1.4;">${descLabel}</p>
                        
                        <div id="settings-error" class="glass-panel" style="display: none; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); color: #f87171; padding: 12px; border-radius: 8px; margin-bottom: 15px; font-size: 13px;"></div>
                        
                        <div class="settings-group mb-4" style="display: flex; flex-direction: column; gap: 12px;">
                            <div>
                                <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 5px;">${ipLabel}:</label>
                                <input type="text" id="km-router-ip" value="${router_ip}" placeholder="192.168.1.1" style="width: 100%; background: #020617; border: 1px solid var(--border-color); color: white; padding: 10px; border-radius: 6px; outline: none; font-size: 13px;">
                            </div>
                            
                            <div style="display: flex; gap: 12px;">
                                <div style="flex: 1;">
                                    <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 5px;">${loginLabel}:</label>
                                    <input type="text" id="km-router-login" value="${router_login}" placeholder="admin" style="width: 100%; background: #020617; border: 1px solid var(--border-color); color: white; padding: 10px; border-radius: 6px; outline: none; font-size: 13px;">
                                </div>
                                <div style="flex: 1;">
                                    <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 5px;">${pwdLabel}:</label>
                                    <input type="password" id="km-router-pwd" value="${has_password ? '******' : ''}" placeholder="${has_password ? '••••••••' : 'Пароль'}" style="width: 100%; background: #020617; border: 1px solid var(--border-color); color: white; padding: 10px; border-radius: 6px; outline: none; font-size: 13px;">
                                </div>
                            </div>
                            
                            <div style="display: flex; gap: 12px; margin-top: 5px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 15px;">
                                <div style="flex: 1;">
                                    <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 5px;">${portLabel}:</label>
                                    <input type="number" id="km-mihomo-port" value="${mihomo_port}" placeholder="9097" style="width: 100%; background: #020617; border: 1px solid var(--border-color); color: white; padding: 10px; border-radius: 6px; outline: none; font-size: 13px;">
                                </div>
                                <div style="flex: 1;">
                                    <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 5px;">${secLabel}:</label>
                                    <input type="password" id="km-mihomo-sec" value="${has_secret ? '******' : ''}" placeholder="${has_secret ? '••••••••' : 'Токен'}" style="width: 100%; background: #020617; border: 1px solid var(--border-color); color: white; padding: 10px; border-radius: 6px; outline: none; font-size: 13px;">
                                </div>
                            </div>
                        </div>
                        
                        <button class="plugin-btn" style="width: 100%; background: var(--accent); color: white; margin-top: 15px;" id="km-save-btn">
                            ${t('btn_save_changes', 'Сохранить изменения')}
                        </button>
                    </div>
                `;
                modalContent.innerHTML = html;
                
                modalContent.querySelector('#km-save-btn').onclick = () => {
                    const btn = modalContent.querySelector('#km-save-btn');
                    const errorDiv = modalContent.querySelector('#settings-error');
                    
                    if (errorDiv) errorDiv.style.display = 'none';
                    btn.disabled = true;
                    btn.style.opacity = '0.6';
                    btn.textContent = t('btn_validating', 'Проверка соединения...');
                    
                    socket.emit('plugin_command', {
                        plugin_id: 'keenetic_mihomo',
                        action: 'save_settings',
                        data: {
                            router_ip: modalContent.querySelector('#km-router-ip').value,
                            router_login: modalContent.querySelector('#km-router-login').value,
                            router_password: modalContent.querySelector('#km-router-pwd').value,
                            mihomo_port: modalContent.querySelector('#km-mihomo-port').value,
                            mihomo_secret: modalContent.querySelector('#km-mihomo-sec').value
                        }
                    });
                };
            } else if (payload.event === 'settings_validation_result') {
                const btn = modalContent.querySelector('#km-save-btn');
                const errorDiv = modalContent.querySelector('#settings-error');
                
                if (payload.data.success) {
                    showToast(t('settings_saved_success', 'Настройки сохранены и проверены!'));
                    closeModal();
                } else {
                    if (btn) {
                        btn.disabled = false;
                        btn.style.opacity = '1';
                        btn.textContent = t('btn_save_changes', 'Сохранить изменения');
                    }
                    if (errorDiv) {
                        errorDiv.style.display = 'block';
                        errorDiv.textContent = payload.data.message;
                    }
                }
            }
        }
    },
    'sentinel_music': {
        render: (config) => {
            modalContent.innerHTML = `<div class="loading-spinner"></div>`;
            socket.emit('plugin_command', { plugin_id: 'sentinel_music', action: 'get_settings_data', data: {} });
        },
        onEvent: (payload) => {
            if (payload.event === 'settings_data') {
                const { server_url, has_token, username, is_authenticated, is_connected, devices } = payload.data;
                const statusBadge = is_authenticated
                    ? (is_connected 
                        ? `<span style="display:inline-block; padding:4px 10px; border-radius:12px; background:rgba(34,197,94,0.15); color:#4ade80; font-size:12px; font-weight:500;">🟢 ${t('sentinel_connected', 'Подключено')} (${username})</span>`
                        : `<span style="display:inline-block; padding:4px 10px; border-radius:12px; background:rgba(234,179,8,0.15); color:#facc15; font-size:12px; font-weight:500;">🟡 ${t('sentinel_connecting', 'Авторизован, соединение...')}</span>`)
                    : `<span style="display:inline-block; padding:4px 10px; border-radius:12px; background:rgba(239,68,68,0.15); color:#f87171; font-size:12px; font-weight:500;">🔴 ${t('sentinel_auth_required', 'Требуется авторизация')}</span>`;

                let html = `
                    <div class="sentinel-settings" style="text-align: left;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                            <span style="font-size: 13px; color: var(--text-muted);">${t('desc_sentinel_settings', 'Подключение к Sentinel Music Server & Sentinel Connect')}</span>
                            ${statusBadge}
                        </div>
                        
                        <div id="sentinel-error" class="glass-panel" style="display: none; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); color: #f87171; padding: 12px; border-radius: 8px; margin-bottom: 15px; font-size: 13px;"></div>

                        <div class="settings-group mb-4" style="display: flex; flex-direction: column; gap: 12px;">
                            <div>
                                <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 5px;">${t('label_sentinel_url', 'URL сервера Sentinel')}:</label>
                                <input type="text" id="sm-server-url" value="${server_url || 'http://127.0.0.1:8000'}" placeholder="http://127.0.0.1:8000" style="width: 100%; background: #020617; border: 1px solid var(--border-color); color: white; padding: 10px; border-radius: 6px; outline: none; font-size: 13px;">
                            </div>

                            <div style="border-top: 1px solid rgba(255,255,255,0.05); padding-top: 12px;">
                                <div style="display: flex; gap: 10px; margin-bottom: 12px;">
                                    <button type="button" id="tab-login-btn" style="flex: 1; padding: 8px; border-radius: 6px; background: var(--accent); color: white; border: none; font-size: 12px; cursor: pointer;">Логин и пароль</button>
                                    <button type="button" id="tab-token-btn" style="flex: 1; padding: 8px; border-radius: 6px; background: rgba(255,255,255,0.05); color: var(--text-muted); border: 1px solid var(--border-color); font-size: 12px; cursor: pointer;">Токен сессии</button>
                                </div>

                                <div id="container-login" style="display: flex; flex-direction: column; gap: 10px;">
                                    <div>
                                        <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 5px;">Логин:</label>
                                        <input type="text" id="sm-username" value="${username || ''}" placeholder="username" style="width: 100%; background: #020617; border: 1px solid var(--border-color); color: white; padding: 10px; border-radius: 6px; outline: none; font-size: 13px;">
                                    </div>
                                    <div>
                                        <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 5px;">Пароль:</label>
                                        <input type="password" id="sm-password" value="${has_token ? '******' : ''}" placeholder="${has_token ? '••••••••' : 'Пароль'}" style="width: 100%; background: #020617; border: 1px solid var(--border-color); color: white; padding: 10px; border-radius: 6px; outline: none; font-size: 13px;">
                                    </div>
                                </div>

                                <div id="container-token" style="display: none; flex-direction: column; gap: 10px;">
                                    <div>
                                        <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 5px;">Session Token (enc:v1:... или токен):</label>
                                        <input type="password" id="sm-token" value="${has_token ? '******' : ''}" placeholder="${has_token ? '••••••••' : 'Вставьте токен'}" style="width: 100%; background: #020617; border: 1px solid var(--border-color); color: white; padding: 10px; border-radius: 6px; outline: none; font-size: 13px;">
                                    </div>
                                </div>
                            </div>
                        </div>

                        ${devices && devices.length ? `
                            <div style="margin-top: 15px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 12px;">
                                <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 8px;">Активные плееры Sentinel (${devices.length}):</label>
                                <div style="display: flex; flex-direction: column; gap: 6px; max-height: 120px; overflow-y: auto;">
                                    ${devices.map(d => `
                                        <div class="glass-panel" style="display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; font-size: 12px;">
                                            <span>${d.name}</span>
                                            <span style="color: ${d.playing ? '#4ade80' : 'var(--text-muted)'}; font-size: 11px;">${d.playing ? '▶ Играет' : '⏸ Пауза'}</span>
                                        </div>
                                    `).join('')}
                                </div>
                            </div>
                        ` : ''}

                        <div style="display: flex; gap: 10px; margin-top: 20px;">
                            <button class="plugin-btn" style="flex: 2; background: var(--accent); color: white;" id="sm-save-btn">
                                ${t('btn_save_and_connect', 'Сохранить и подключиться')}
                            </button>
                            ${has_token ? `
                                <button class="plugin-btn" style="flex: 1; background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.3);" id="sm-logout-btn">
                                    ${t('btn_logout', 'Выйти')}
                                </button>
                            ` : ''}
                        </div>
                    </div>
                `;
                modalContent.innerHTML = html;

                // Tab switching
                const tabLogin = modalContent.querySelector('#tab-login-btn');
                const tabToken = modalContent.querySelector('#tab-token-btn');
                const contLogin = modalContent.querySelector('#container-login');
                const contToken = modalContent.querySelector('#container-token');

                if (tabLogin && tabToken) {
                    tabLogin.onclick = () => {
                        tabLogin.style.background = 'var(--accent)';
                        tabLogin.style.color = 'white';
                        tabToken.style.background = 'rgba(255,255,255,0.05)';
                        tabToken.style.color = 'var(--text-muted)';
                        contLogin.style.display = 'flex';
                        contToken.style.display = 'none';
                    };

                    tabToken.onclick = () => {
                        tabToken.style.background = 'var(--accent)';
                        tabToken.style.color = 'white';
                        tabLogin.style.background = 'rgba(255,255,255,0.05)';
                        tabLogin.style.color = 'var(--text-muted)';
                        contToken.style.display = 'flex';
                        contLogin.style.display = 'none';
                    };
                }

                // Save button
                modalContent.querySelector('#sm-save-btn').onclick = () => {
                    const btn = modalContent.querySelector('#sm-save-btn');
                    const errorDiv = modalContent.querySelector('#sentinel-error');
                    if (errorDiv) errorDiv.style.display = 'none';
                    btn.disabled = true;
                    btn.style.opacity = '0.6';
                    btn.textContent = t('btn_validating', 'Проверка соединения...');

                    const serverUrl = modalContent.querySelector('#sm-server-url').value;
                    const username = modalContent.querySelector('#sm-username').value;
                    const password = modalContent.querySelector('#sm-password').value;
                    const token = modalContent.querySelector('#sm-token').value;

                    socket.emit('plugin_command', {
                        plugin_id: 'sentinel_music',
                        action: 'save_settings',
                        data: {
                            server_url: serverUrl,
                            username: username,
                            password: password,
                            token: token
                        }
                    });
                };

                // Logout button
                const logoutBtn = modalContent.querySelector('#sm-logout-btn');
                if (logoutBtn) {
                    logoutBtn.onclick = () => {
                        socket.emit('plugin_command', { plugin_id: 'sentinel_music', action: 'logout', data: {} });
                        modalContent.innerHTML = '<div class="loading-spinner"></div>';
                    };
                }
            } else if (payload.event === 'settings_validation_result') {
                const btn = modalContent.querySelector('#sm-save-btn');
                const errorDiv = modalContent.querySelector('#sentinel-error');
                
                if (payload.data.success) {
                    showToast(payload.data.message || t('settings_saved_success', 'Настройки сохранены!'));
                    closeModal();
                } else {
                    if (btn) {
                        btn.disabled = false;
                        btn.style.opacity = '1';
                        btn.textContent = t('btn_save_and_connect', 'Сохранить и подключиться');
                    }
                    if (errorDiv) {
                        errorDiv.style.display = 'block';
                        errorDiv.textContent = payload.data.message;
                    }
                }
            }
        }
    }
};

// Internal App Launcher UI Logic
function renderAppLauncherUI(config) {
    const widgets = config.widgets || [];
    const launcherWidget = widgets.find(w => w.id === "app_buttons") || widgets[0];
    const apps = launcherWidget ? (launcherWidget.buttons || []) : [];

    let html = `
        <div class="launcher-settings">
            <div class="settings-group" style="margin-bottom: 20px;">
                <h4 style="color: var(--accent); margin-bottom: 10px;">${t('label_current_apps', 'Текущие приложения')}</h4>
                <div class="apps-list" id="launcher-apps-list" style="display: flex; flex-direction: column; gap: 8px; max-height: 260px; overflow-y: auto; padding-right: 5px;">
                    ${apps.map((app, index) => `
                        <div class="glass-panel" draggable="true" data-index="${index}" style="display: flex; align-items: center; justify-content: space-between; padding: 10px; cursor: grab;">
                            <div style="display: flex; align-items: center; gap: 12px; pointer-events: none;">
                                <div style="color: var(--text-muted); font-size: 14px; margin-right: 5px;">☰</div>
                                <div style="width: 52px; height: 52px; display: flex; align-items: center; justify-content: center; overflow: hidden;">
                                    ${getLauncherIconHtml(app.icon)}
                                </div>
                                <div style="text-align: left;">
                                    <div style="font-weight: 500; color: white;">${app.label}</div>
                                    <div style="font-size: 10px; color: var(--text-muted); word-break: break-all; max-width: 200px;">
                                        <span style="color: var(--accent); font-weight: bold; text-transform: uppercase;">[${app.action || 'launch'}]</span> ${app.data}
                                    </div>
                                </div>
                            </div>
                            <button class="plugin-btn remove-app-btn" style="background: rgba(239, 68, 68, 0.1); color: #ef4444; border-color: rgba(239, 68, 68, 0.2); padding: 5px 10px;" data-label="${app.label}">✕</button>
                        </div>
                    `).join('') || `<p style="color: var(--text-muted);">${t('no_apps_added', 'Приложения не добавлены')}</p>`}
                </div>
            </div>
            
            <div class="settings-group glass-panel" style="padding: 15px; border: 1px solid var(--accent-glow);">
                <h4 style="color: var(--accent); margin-bottom: 12px;">${t('label_add_new', 'Добавить новое')}</h4>
                
                <!-- Тип действия (Макроса) -->
                <div style="margin-bottom: 15px;">
                    <label style="font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 5px; text-transform: uppercase; letter-spacing: 0.5px;">Тип действия:</label>
                    <select id="new-app-action" style="width: 100%; background: #020617; border: 1px solid var(--border-color); color: white; padding: 10px; border-radius: 6px; outline: none; cursor: pointer; font-size: 13px;">
                        <option value="launch">🚀 Запуск приложения или файла</option>
                        <option value="hotkey">⌨️ Горячие клавиши (Keyboard Hotkeys)</option>
                        <option value="command">💻 Команда консоли / Фоновый скрипт</option>
                        <option value="media">🎵 Управление медиа / Громкость</option>
                        <option value="system">🔒 Системное действие (Блокировка / Микрофон)</option>
                    </select>
                </div>

                <div style="display: flex; gap: 15px; align-items: flex-start;">
                    <div id="new-app-icon-preview" style="width: 64px; height: 64px; background: rgba(255,255,255,0.05); border-radius: 12px; display: flex; align-items: center; justify-content: center; overflow: hidden; border: 1px dashed var(--border-color); flex-shrink: 0;">
                        <span style="font-size: 24px; opacity: 0.3;">🚀</span>
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 10px; flex-grow: 1;">
                        <input type="text" id="new-app-name" placeholder="Название кнопки (например: Discord Mute)" style="width: 100%; background: #020617; border: 1px solid var(--border-color); color: white; padding: 8px; border-radius: 4px; font-size: 13px;">
                        
                        <!-- Контейнер для динамического ввода значения в зависимости от экшена -->
                        <div id="new-app-input-container" style="width: 100%;">
                            <!-- Заполняется динамически через JS -->
                        </div>
                    </div>
                </div>
                <button class="plugin-btn" style="width: 100%; background: var(--accent); color: white; margin-top: 15px;" id="add-app-btn">${t('btn_add_to_list', '+ Добавить')}</button>
            </div>
        </div>
    `;
    modalContent.innerHTML = html;

    const actionSelect = modalContent.querySelector('#new-app-action');
    const inputContainer = modalContent.querySelector('#new-app-input-container');
    const previewDiv = modalContent.querySelector('#new-app-icon-preview');

    // Функция обновления полей ввода в зависимости от выбранного экшена
    const updateInputs = () => {
        const action = actionSelect.value;
        
        // Обновляем иконку по умолчанию в превью
        const emojis = {
            launch: "🚀",
            hotkey: "⌨️",
            command: "💻",
            media: "🎵",
            system: "🔒"
        };
        previewDiv.innerHTML = `<span style="font-size: 24px; opacity: 0.3;">${emojis[action] || "🚀"}</span>`;

        if (action === "launch") {
            inputContainer.innerHTML = `
                <div style="display: flex; gap: 5px;">
                    <input type="text" id="new-app-path" placeholder="Путь к файлу/ярлыку или команда запуска" style="flex-grow: 1; background: #020617; border: 1px solid var(--border-color); color: white; padding: 8px; border-radius: 4px; font-size: 13px;">
                    <button class="plugin-btn" id="browse-app-btn" style="padding: 5px 12px; background: rgba(56, 189, 248, 0.2); color: #38bdf8; border-color: rgba(56, 189, 248, 0.3);">📁</button>
                </div>
            `;
            modalContent.querySelector('#browse-app-btn').onclick = () => socket.emit('plugin_command', { plugin_id: 'app_launcher', action: 'browse_file', data: {} });
        } else if (action === "hotkey") {
            inputContainer.innerHTML = `
                <input type="text" id="new-app-path" placeholder="Кликните сюда и нажмите клавиши на клавиатуре..." style="width: 100%; background: #020617; border: 1px solid var(--border-color); color: white; padding: 10px; border-radius: 4px; font-size: 13px; cursor: pointer; caret-color: transparent; border-color: var(--accent);" readonly>
            `;
            
            const pathInput = inputContainer.querySelector('#new-app-path');
            
            // Функция маппинга физических кодов клавиш (независимо от раскладки)
            const mapCodeToKey = (code) => {
                if (!code) return "";
                if (code.startsWith("Key")) return code.replace("Key", "").toLowerCase();
                if (code.startsWith("Digit")) return code.replace("Digit", "");
                if (code.startsWith("F") && !isNaN(code.substring(1))) return code.toLowerCase();
                
                const mapping = {
                    "ControlLeft": "ctrl", "ControlRight": "ctrl",
                    "ShiftLeft": "shift", "ShiftRight": "shift",
                    "AltLeft": "alt", "AltRight": "alt",
                    "MetaLeft": "win", "MetaRight": "win",
                    "Space": "space", "Escape": "esc", "Enter": "enter", "Tab": "tab",
                    "Backspace": "backspace", "Delete": "delete",
                    "ArrowUp": "up", "ArrowDown": "down", "ArrowLeft": "left", "ArrowRight": "right"
                };
                return mapping[code] || "";
            };
            
            pathInput.onfocus = () => {
                pathInput.value = "";
                pathInput.placeholder = "Запись комбинации... Отпустите клавиши для сохранения";
                pathInput.style.borderColor = "#10b981"; // Зеленая рамка при записи
                pathInput.style.boxShadow = "0 0 10px rgba(16, 185, 129, 0.3)";
            };
            
            pathInput.onblur = () => {
                pathInput.style.borderColor = "var(--border-color)";
                pathInput.style.boxShadow = "none";
                if (!pathInput.value) {
                    pathInput.placeholder = "Кликните сюда и нажмите клавиши на клавиатуре...";
                }
            };
            
            pathInput.onkeydown = (e) => {
                e.preventDefault();
                e.stopPropagation();
                
                const keys = [];
                if (e.ctrlKey) keys.push("ctrl");
                if (e.shiftKey) keys.push("shift");
                if (e.altKey) keys.push("alt");
                if (e.metaKey) keys.push("win");
                
                const cleanKey = mapCodeToKey(e.code);
                if (cleanKey && !["ctrl", "shift", "alt", "win"].includes(cleanKey)) {
                    keys.push(cleanKey);
                }
                
                if (keys.length > 0) {
                    pathInput.value = keys.join("+");
                }
            };
        } else if (action === "command") {
            inputContainer.innerHTML = `
                <input type="text" id="new-app-path" placeholder="Системный скрипт/команда (например: ipconfig /flushdns)" style="width: 100%; background: #020617; border: 1px solid var(--border-color); color: white; padding: 8px; border-radius: 4px; font-size: 13px;">
            `;
        } else if (action === "media") {
            inputContainer.innerHTML = `
                <select id="new-app-path" style="width: 100%; background: #020617; border: 1px solid var(--border-color); color: white; padding: 8px; border-radius: 4px; outline: none; cursor: pointer; font-size: 13px;">
                    <option value="play_pause">Play / Pause (Воспроизведение/Пауза)</option>
                    <option value="next">Next Track (Следующий трек)</option>
                    <option value="prev">Previous Track (Предыдущий трек)</option>
                    <option value="volume_up">Volume Up (Прибавить громкость)</option>
                    <option value="volume_down">Volume Down (Убавить громкость)</option>
                    <option value="mute">Mute Output (Заглушить динамики)</option>
                </select>
            `;
        } else if (action === "system") {
            inputContainer.innerHTML = `
                <select id="new-app-path" style="width: 100%; background: #020617; border: 1px solid var(--border-color); color: white; padding: 8px; border-radius: 4px; outline: none; cursor: pointer; font-size: 13px;">
                    <option value="lock">Lock PC (Заблокировать рабочую станцию)</option>
                    <option value="sleep">Sleep Mode (Отправить ПК в режим сна)</option>
                    <option value="mute_mic">Toggle Mic Mute (Вкл/Выкл микрофон)</option>
                </select>
            `;
        }
    };

    // Привязываем события
    actionSelect.onchange = updateInputs;
    updateInputs(); // Инициализация первого выбора

    // Добавление кнопки
    modalContent.querySelector('#add-app-btn').onclick = () => {
        const name = document.getElementById('new-app-name').value;
        const path = document.getElementById('new-app-path').value;
        const actionType = actionSelect.value;
        const iconImg = previewDiv.querySelector('img');
        
        if (!name || !path) return;
        
        socket.emit('plugin_command', { 
            plugin_id: 'app_launcher', 
            action: 'add_app', 
            data: { 
                label: name, 
                path: path, 
                action: actionType,
                icon: iconImg ? iconImg.src : null 
            } 
        });
        modalContent.innerHTML = '<div class="loading-spinner"></div>';
    };

    // Удаление кнопок
    modalContent.querySelectorAll('.remove-app-btn').forEach(btn => {
        btn.onclick = () => {
            const label = btn.getAttribute('data-label');
            if (confirm(`${t('confirm_delete', 'Удалить')} "${label}"?`)) {
                socket.emit('plugin_command', { plugin_id: 'app_launcher', action: 'remove_app', data: label });
            }
        };
    });
}

function getLauncherIconHtml(iconData) {
    if (iconData && iconData.startsWith('data:image')) {
        return `<img src="${iconData}" style="width: 100%; height: 100%; object-fit: contain; transform: scale(1.15);">`;
    }
    
    // Карта эмодзи-иконок для кастомных макро-действий
    const emojiMap = {
        "Lock": "🔒",
        "Moon": "🌙",
        "Play": "⏯️",
        "SkipForward": "⏭️",
        "MicOff": "🎙️❌",
        "VolumeX": "🔇",
        "Monitor": "🖥️",
        "Activity": "📈",
        "XSquare": "🛑",
        "Terminal": "⌨️",
        "Code": "💻",
        "Music": "🎵",
        "AppWindow": "🪟"
    };
    
    if (iconData && emojiMap[iconData]) {
        return `<span style="font-size: 24px;">${emojiMap[iconData]}</span>`;
    }
    return `<span style="font-size: 20px;">🚀</span>`;
}
