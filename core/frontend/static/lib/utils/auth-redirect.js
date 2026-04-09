/**
 * Редирект на страницу входа (общий для PlatformApp и обработки 401).
 */
export function redirectToLogin() {
    const currentPath = window.location.pathname;
    if (currentPath === '/login' || currentPath === '/frontend/login') {
        return;
    }

    const currentUrl = window.location.href;
    const currentHost = window.location.host;
    const protocol = window.location.protocol;

    const parts = currentHost.split('.');
    const lastSegment = parts[parts.length - 1];
    let loginHost;

    if (lastSegment.includes(':')) {
        const [hostOnly, _port] = lastSegment.split(':');
        parts[parts.length - 1] = hostOnly;
        const baseDomain = parts.slice(-2).join('.');
        loginHost = `${baseDomain}:8002`;
    } else {
        loginHost = currentHost;
    }

    const loginUrl = `${protocol}//${loginHost}/login?redirect_uri=${encodeURIComponent(currentUrl)}`;
    window.location.href = loginUrl;
}
