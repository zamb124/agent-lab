/**
 * Оболочки, где нельзя открывать сервисы через window.open (новое окно / Safari):
 * PWA standalone и нативный Capacitor (iOS/Android).
 *
 * Нативный мост Capacitor доступен в странице раньше, чем полностью заполняется
 * window.Capacitor.isNativePlatform (см. @capacitor/core getPlatformId): iOS —
 * window.webkit.messageHandlers.bridge, Android — window.androidBridge.
 */

export function isCapacitorNativePlatform() {
    if (typeof window === 'undefined') {
        return false;
    }
    if (typeof window.Capacitor === 'undefined' || typeof window.Capacitor.isNativePlatform !== 'function') {
        return false;
    }
    return window.Capacitor.isNativePlatform();
}

/**
 * Полная загрузка нового документа в нативном Capacitor: слой SplashScreen, затем assign.
 * В PWA/браузере — обычный assign.
 */
export function assignInNativeShell(href) {
    if (typeof window === 'undefined') {
        return;
    }
    if (!isCapacitorNativePlatform()) {
        window.location.assign(href);
        return;
    }
    void import('@capacitor/splash-screen')
        .then(({ SplashScreen }) => SplashScreen.show({ autoHide: false }))
        .then(() => {
            window.location.assign(href);
        })
        .catch(() => {
            window.location.assign(href);
        });
}

export function isStandaloneOrNativeAppShell() {
    if (typeof window === 'undefined') {
        return false;
    }
    if (window.androidBridge) {
        return true;
    }
    if (window.webkit?.messageHandlers?.bridge) {
        return true;
    }
    const mediaQuery = window.matchMedia?.('(display-mode: standalone)');
    if (mediaQuery && mediaQuery.matches) {
        return true;
    }
    if (window.navigator.standalone === true) {
        return true;
    }
    if (typeof window.Capacitor !== 'undefined' && typeof window.Capacitor.isNativePlatform === 'function') {
        return window.Capacitor.isNativePlatform();
    }
    return false;
}

function _hostnameOnly(host) {
    const part = host.split(':')[0];
    return part.toLowerCase();
}

function _sameProductSiteHostnames(a, b) {
    const h1 = _hostnameOnly(a);
    const h2 = _hostnameOnly(b);
    if (h1 === h2) {
        return true;
    }
    const suffixes = ['.humanitec.ru', '.humanetic.ru', '.agents-lab.ru'];
    for (const s of suffixes) {
        if (h1.endsWith(s) && h2.endsWith(s)) {
            return true;
        }
    }
    if (h1.endsWith('.lvh.me') && h2.endsWith('.lvh.me')) {
        return true;
    }
    if (
        (h1 === 'localhost' || h1.endsWith('.localhost')) &&
        (h2 === 'localhost' || h2.endsWith('.localhost'))
    ) {
        return true;
    }
    if (h1 === '127.0.0.1' && h2 === '127.0.0.1') {
        return true;
    }
    return false;
}

/**
 * Тот же продукт (тенанты на поддоменах, dev-хосты), не внешний сайт.
 */
export function isInternalProductNavigationUrl(targetUrl) {
    if (targetUrl.protocol !== 'http:' && targetUrl.protocol !== 'https:') {
        return false;
    }
    const cur = window.location;
    if (targetUrl.origin === cur.origin) {
        return true;
    }
    return _sameProductSiteHostnames(targetUrl.hostname, cur.hostname);
}

let _windowOpenPatched = false;

/**
 * Подмена window.open: во встроенном браузере Capacitor вызов с URL того же продукта
 * иначе уходит в отдельное окно / системный Safari. Глобально перенаправляем в текущий WebView.
 */
export function installNativeAppShellWindowOpenPatch() {
    if (_windowOpenPatched || typeof window === 'undefined') {
        return;
    }
    _windowOpenPatched = true;

    const originalOpen = window.open;

    window.open = function (url, target, features) {
        if (!isStandaloneOrNativeAppShell()) {
            return originalOpen.call(window, url, target, features);
        }
        if (url === undefined || url === null) {
            return originalOpen.call(window, url, target, features);
        }
        if (typeof url !== 'string') {
            return originalOpen.call(window, url, target, features);
        }
        if (url === '') {
            return originalOpen.call(window, url, target, features);
        }
        let parsed;
        try {
            parsed = new URL(url, window.location.href);
        } catch {
            return originalOpen.call(window, url, target, features);
        }
        if (isInternalProductNavigationUrl(parsed)) {
            assignInNativeShell(parsed.href);
            return null;
        }
        return originalOpen.call(window, url, target, features);
    };
}

let _linkCaptureInstalled = false;

/**
 * Перехватывает клики по <a href> (в т.ч. target=_blank) на внутренние URL продукта,
 * чтобы в Capacitor / standalone не уходить в системный браузер.
 *
 * Регистрируется всегда один раз: мост Capacitor появляется после первого импорта модулей;
 * если проверять оболочку только при install — слушатель не ставился бы никогда.
 */
export function installNativeAppShellLinkCapture() {
    if (_linkCaptureInstalled) {
        return;
    }
    _linkCaptureInstalled = true;

    document.addEventListener(
        'click',
        (event) => {
            if (!isStandaloneOrNativeAppShell()) {
                return;
            }
            if (event.defaultPrevented) {
                return;
            }
            const el = event.target?.closest?.('a[href]');
            if (!el || !el.href) {
                return;
            }
            if (el.getAttribute('download') != null) {
                return;
            }
            let url;
            try {
                url = new URL(el.href);
            } catch {
                return;
            }
            if (!isInternalProductNavigationUrl(url)) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            assignInNativeShell(el.href);
        },
        true,
    );
}

export function openUrlSameWindowOrTab(url) {
    if (isStandaloneOrNativeAppShell()) {
        assignInNativeShell(url);
        return;
    }
    window.open(url, '_blank', 'noopener,noreferrer');
}
