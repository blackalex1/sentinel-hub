const modal = document.getElementById('action-modal');
const modalTitle = document.getElementById('modal-title');
const modalContent = document.getElementById('modal-content');
const modalCloseBtn = document.getElementById('modal-close');

if (modalCloseBtn) modalCloseBtn.onclick = closeModal;

export function showModal({ title, content, onRender }) {
    if (modalTitle) modalTitle.textContent = title;
    if (modalContent) modalContent.innerHTML = content;
    modal.classList.remove('hidden');
    if (onRender) onRender(modalContent);
}

export function closeModal() {
    modal.classList.add('hidden');
}

export function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'error') icon = '❌';
    if (type === 'warning') icon = '⚠️';

    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(50px)';
        setTimeout(() => toast.remove(), 400);
    }, 4000);
}

export function applyThemeColor(hex) {
    if (!hex) return;

    let cssColor = hex;
    if (hex.startsWith('0xFF')) {
        cssColor = '#' + hex.substring(4);
    } else if (hex.startsWith('0x')) {
        cssColor = '#' + hex.substring(2);
    }

    document.documentElement.style.setProperty('--accent', cssColor);

    if (cssColor.startsWith('#')) {
        const r = parseInt(cssColor.substring(1, 3), 16);
        const g = parseInt(cssColor.substring(3, 5), 16);
        const b = parseInt(cssColor.substring(5, 7), 16);
        document.documentElement.style.setProperty('--accent-glow', `rgba(${r}, ${g}, ${b}, 0.5)`);
    }
}

export function initNavigation() {
    document.querySelectorAll('.nav-links a').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            document.querySelectorAll('.nav-links li').forEach(li => li.classList.remove('active'));
            e.target.parentElement.classList.add('active');

            const targetId = e.target.getAttribute('data-target');
            document.querySelectorAll('.content-section').forEach(sec => sec.classList.remove('active'));
            document.getElementById(targetId).classList.add('active');
        });
    });
}
