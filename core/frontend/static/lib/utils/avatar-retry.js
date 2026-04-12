/**
 * Механизм retry-загрузки аватаров с exponential backoff.
 *
 * Если внешний CDN (например avatars.yandex.net) временно недоступен
 * (ERR_SOCKET_NOT_CONNECTED и аналогичные сетевые ошибки), браузерный
 * <img> получает onerror и навсегда показывает fallback. Этот модуль
 * позволяет перезапросить картинку до MAX_ATTEMPTS раз с нарастающей
 * задержкой, а при окончательном провале — записать диагностику и
 * отправить событие для телеметрии.
 */

const MAX_ATTEMPTS = 5;
const BACKOFF_DELAYS_MS = [1000, 2000, 4000, 8000, 16000];

/**
 * Создаёт контроллер retry-загрузки для одного <img>.
 *
 * Использование в Lit-компоненте:
 *
 *   constructor() {
 *       super();
 *       this._avatarRetry = createAvatarRetry(() => this.requestUpdate());
 *   }
 *
 *   disconnectedCallback() {
 *       super.disconnectedCallback();
 *       this._avatarRetry.cancel();
 *   }
 *
 *   _renderAvatar(url) {
 *       const src = this._avatarRetry.currentSrc(url);
 *       if (!src) return html`<fallback />`;
 *       return html`<img src=${src}
 *                        @load=${() => this._avatarRetry.onLoad()}
 *                        @error=${() => this._avatarRetry.onError(url)} />`;
 *   }
 *
 * @param {() => void} requestUpdate — колбэк для ререндера компонента
 * @returns {AvatarRetryController}
 */
export function createAvatarRetry(requestUpdate) {
    let attempt = 0;
    let failed = false;
    let loaded = false;
    let timerId = null;
    let activeUrl = null;
    let bustSuffix = '';

    function cancel() {
        if (timerId !== null) {
            clearTimeout(timerId);
            timerId = null;
        }
    }

    function reset() {
        cancel();
        attempt = 0;
        failed = false;
        loaded = false;
        bustSuffix = '';
    }

    /**
     * Возвращает текущий src для <img> или null если все попытки исчерпаны.
     * При смене исходного URL автоматически сбрасывает счётчики.
     */
    function currentSrc(originalUrl) {
        if (typeof originalUrl !== 'string' || originalUrl.trim() === '') {
            return null;
        }
        if (originalUrl !== activeUrl) {
            reset();
            activeUrl = originalUrl;
        }
        if (failed) {
            return null;
        }
        if (bustSuffix === '') {
            return originalUrl;
        }
        const separator = originalUrl.includes('?') ? '&' : '?';
        return `${originalUrl}${separator}_retry=${bustSuffix}`;
    }

    function onLoad() {
        cancel();
        loaded = true;
        attempt = 0;
        bustSuffix = '';
    }

    function onError(originalUrl) {
        if (failed || loaded) {
            return;
        }
        attempt += 1;
        if (attempt >= MAX_ATTEMPTS) {
            failed = true;
            cancel();
            _emitAvatarLoadFailed(originalUrl, attempt);
            requestUpdate();
            return;
        }
        const delay = BACKOFF_DELAYS_MS[attempt - 1] ?? BACKOFF_DELAYS_MS[BACKOFF_DELAYS_MS.length - 1];
        cancel();
        timerId = setTimeout(() => {
            timerId = null;
            bustSuffix = `${attempt}.${Date.now()}`;
            requestUpdate();
        }, delay);
    }

    /** true если аватар окончательно не загрузился после всех попыток */
    function isFailed() {
        return failed;
    }

    return { currentSrc, onLoad, onError, cancel, reset, isFailed };
}

function _emitAvatarLoadFailed(url, attempts) {
    console.warn(
        '[platform:avatar] load failed',
        JSON.stringify({
            url,
            attempts,
            online: navigator.onLine,
            visibility: document.visibilityState,
        }),
    );
    window.dispatchEvent(
        new CustomEvent('platform:avatar-load-failed', {
            detail: { url, attempts, online: navigator.onLine },
        }),
    );
}
