export function getAuthToken() {
    // 1. Приоритет - токен в куках (устанавливается GUI)
    const cookieToken = document.cookie.split('; ').find(row => row.startsWith('gui_token='))?.split('=')[1];
    if (cookieToken) return cookieToken;

    // 2. Затем URL параметры (для внешней отладки)
    const urlParams = new URLSearchParams(window.location.search);
    const urlToken = urlParams.get('gui_token') || urlParams.get('token');
    if (urlToken) return urlToken;

    // 3. Затем localStorage (сохраненный токен для внешних девайсов)
    return localStorage.getItem('auth_token');
}

export async function secureFetch(url, options = {}) {
    const token = getAuthToken();
    const headers = {
        'Authorization': `Bearer ${token}`,
        ...options.headers
    };
    return fetch(url, { ...options, headers });
}
