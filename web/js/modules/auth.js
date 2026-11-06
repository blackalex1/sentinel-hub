import { showModal, closeModal, showToast, applyThemeColor } from './ui.js';
import { t } from './i18n.js';
import { getAuthToken } from './api.js';

export function registerAuthHandlers(socket) {
    socket.on('auth_required', () => {
        const token = getAuthToken();
        const message = token ?
            t('auth_gui_token_invalid', "Session invalid or expired. Enter pairing code from PC screen:") :
            t('auth_new_device_detected', "New device detected. Enter pairing code from PC screen:");

        showModal({
            title: t('auth_title', "Authentication"),
            content: `
                <p style="margin-bottom: 15px; color: var(--text-muted);">${message}</p>
                <input type="text" id="auth-code-entry" class="auth-code-input" maxlength="4" placeholder="0000" autofocus>
                <button class="btn btn-primary" style="width: 100%; margin-top: 15px;" id="auth-submit-btn">${t('btn_confirm', 'Confirm')}</button>
            `,
            onRender: (container) => {
                const input = container.querySelector('#auth-code-entry');
                const btn = container.querySelector('#auth-submit-btn');
                
                const submit = () => {
                    const code = input.value;
                    if (code) {
                        socket.emit('auth_attempt', { code: code });
                        closeModal();
                    }
                };

                btn.onclick = submit;
                input.onkeyup = (e) => { if(e.key === 'Enter') submit(); };
                input.focus();
            }
        });
    });

    socket.on('auth_success', (data) => {
        console.log("Authorized successfully!");
        if (data.token) {
            localStorage.setItem('auth_token', data.token);
        }
        if (data.encryption_key) {
            localStorage.setItem('encryption_key', data.encryption_key);
        }
        if (data.theme_color) {
            applyThemeColor(data.theme_color);
        }
        showToast(t('auth_success_msg', "Authorized successfully!"), "success");
    });

    socket.on('auth_error', (data) => {
        showToast(t('auth_failed', "Authorization failed: ") + data.message, "error");
        localStorage.removeItem('auth_token');
        setTimeout(() => location.reload(), 2000);
    });
}
