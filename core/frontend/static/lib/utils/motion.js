/**
 * Хелперы core motion.
 *
 * Анимацией владеет CSS. JS только координирует границы жизненного цикла, чтобы stack
 * компоненты держали DOM смонтированным до завершения браузерной exit-анимации.
 */

export const PLATFORM_MOTION_REDUCED_QUERY = '(prefers-reduced-motion: reduce)';

export function prefersReducedMotion() {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
        return false;
    }
    return window.matchMedia(PLATFORM_MOTION_REDUCED_QUERY).matches;
}

function _parseTimeMs(value) {
    if (typeof value !== 'string' || value.trim().length === 0) return 0;
    return value.split(',').reduce((max, raw) => {
        const token = raw.trim();
        if (token.endsWith('ms')) {
            const n = Number.parseFloat(token.slice(0, -2));
            return Number.isFinite(n) ? Math.max(max, n) : max;
        }
        if (token.endsWith('s')) {
            const n = Number.parseFloat(token.slice(0, -1));
            return Number.isFinite(n) ? Math.max(max, n * 1000) : max;
        }
        return max;
    }, 0);
}

function _maxPairMs(durationValue, delayValue) {
    const durations = String(durationValue || '').split(',');
    const delays = String(delayValue || '').split(',');
    let max = 0;
    for (let i = 0; i < durations.length; i += 1) {
        const duration = _parseTimeMs(durations[i]);
        const delay = _parseTimeMs(delays[i] || delays[delays.length - 1] || '0ms');
        max = Math.max(max, duration + delay);
    }
    return max;
}

export function getCssMotionDurationMs(element) {
    if (!element || typeof getComputedStyle !== 'function') return 0;
    const style = getComputedStyle(element);
    return Math.max(
        _maxPairMs(style.transitionDuration, style.transitionDelay),
        _maxPairMs(style.animationDuration, style.animationDelay),
    );
}

export function waitForPlatformMotion(elements, options = {}) {
    const list = Array.isArray(elements) ? elements.filter(Boolean) : [elements].filter(Boolean);
    if (list.length === 0 || prefersReducedMotion()) {
        return Promise.resolve();
    }

    const fallbackMs = Number.isFinite(options.fallbackMs) ? options.fallbackMs : 240;
    const maxCssMs = list.reduce((max, el) => Math.max(max, getCssMotionDurationMs(el)), 0);
    const maxWaitMs = Math.max(maxCssMs, fallbackMs);
    if (maxWaitMs <= 1) {
        return Promise.resolve();
    }

    return new Promise((resolve) => {
        let done = false;
        let timer = null;
        const pending = new Set(list);
        const finish = () => {
            if (done) return;
            done = true;
            if (timer !== null) clearTimeout(timer);
            for (const el of list) {
                el.removeEventListener('transitionend', onEnd);
                el.removeEventListener('transitioncancel', onEnd);
                el.removeEventListener('animationend', onEnd);
                el.removeEventListener('animationcancel', onEnd);
            }
            resolve();
        };
        const onEnd = (event) => {
            if (!list.includes(event.target)) return;
            pending.delete(event.target);
            if (pending.size === 0) {
                finish();
            }
        };
        for (const el of list) {
            el.addEventListener('transitionend', onEnd);
            el.addEventListener('transitioncancel', onEnd);
            el.addEventListener('animationend', onEnd);
            el.addEventListener('animationcancel', onEnd);
        }
        timer = setTimeout(finish, maxWaitMs + 80);
    });
}
