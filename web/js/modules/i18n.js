import { secureFetch } from './api.js';

export let translations = {};

export async function switchLanguage(lang) {
    try {
        // Мы игнорируем параметр lang и запрашиваем то, что установлено на сервере (унификация)
        // Если нужно именно сменить язык, это делается через api/config
        const res = await secureFetch(`/api/config/translations`);
        translations = await res.json();
        applyTranslations();
        console.log(`Translations updated from server`);
    } catch (err) {
        console.error("Failed to load translations from API", err);
    }
}

export function applyTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (translations[key]) {
            if (el.tagName === 'INPUT' && el.type === 'button') {
                el.value = translations[key];
            } else {
                el.textContent = translations[key];
            }
        }
    });
}

export function t(key, fallback) {
    return translations[key] || fallback || key;
}
