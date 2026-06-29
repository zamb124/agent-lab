/**
 * На узкой ширине (как у мобильного shell) подставляет --app-vh / --app-vw из visualViewport,
 * чтобы fixed-layout и 100%-высота совпадали с видимой областью iOS Safari при съезжающих панелях.
 */

import { installNativeAppShellLinkCapture, installNativeAppShellWindowOpenPatch } from './native-app-shell.js';

installNativeAppShellLinkCapture();
installNativeAppShellWindowOpenPatch();

const MOBILE_SHELL_MQ = '(max-width: 767px)';

/** @type {{ vh: number|null, vw: number|null, offsetTop: number|null, keyboard: boolean|null }} */
let _lastAppliedViewport = {
    vh: null,
    vw: null,
    offsetTop: null,
    keyboard: null,
};

let _viewportRafPending = false;

function applyVisualViewportCssVars() {
    const root = document.documentElement;
    const mq = window.matchMedia(MOBILE_SHELL_MQ);
    if (!mq.matches) {
        _lastAppliedViewport = { vh: null, vw: null, offsetTop: null, keyboard: null };
        root.style.removeProperty('--app-vh');
        root.style.removeProperty('--app-vw');
        root.style.removeProperty('--vv-offset-top');
        root.removeAttribute('data-keyboard-visual');
        return;
    }
    const vv = window.visualViewport;
    if (!vv || typeof vv.height !== 'number') {
        _lastAppliedViewport = { vh: null, vw: null, offsetTop: null, keyboard: null };
        root.style.removeProperty('--app-vh');
        root.style.removeProperty('--app-vw');
        root.style.removeProperty('--vv-offset-top');
        root.removeAttribute('data-keyboard-visual');
        return;
    }
    const vh = Math.round(vv.height);
    const vw = Math.round(vv.width);
    const offsetTop = Math.round(vv.offsetTop);
    const innerH = window.innerHeight;
    const keyboardLikely = innerH > 0 && innerH - vv.height > 80;

    if (
        _lastAppliedViewport.vh === vh
        && _lastAppliedViewport.vw === vw
        && _lastAppliedViewport.offsetTop === offsetTop
        && _lastAppliedViewport.keyboard === keyboardLikely
    ) {
        return;
    }

    _lastAppliedViewport = {
        vh,
        vw,
        offsetTop,
        keyboard: keyboardLikely,
    };

    root.style.setProperty('--app-vh', `${vh}px`);
    root.style.setProperty('--app-vw', `${vw}px`);
    root.style.setProperty('--vv-offset-top', `${offsetTop}px`);

    if (keyboardLikely) {
        root.setAttribute('data-keyboard-visual', '1');
    } else {
        root.removeAttribute('data-keyboard-visual');
    }

    /*
     * iOS: при фокусе в поле Safari сдвигает layout viewport; остаётся window.scrollY и зазор
     * между клавиатурой и нижней панелью. Для platform-shell внешний скролл не нужен.
     * Публичный лендинг (/ , /search) — scrollable; scrollTo(0,0) ломает scroll-to-focused-input.
     * behavior: instant — не полагаться на CSS html (у лендинга может быть scroll-behavior: smooth).
     */
    const landingPublicScroll = root.classList.contains('frontend-landing-public');
    if (
        !landingPublicScroll
        && typeof window.scrollTo === 'function'
        && (window.scrollY !== 0 || window.scrollX !== 0)
    ) {
        try {
            window.scrollTo({ left: 0, top: 0, behavior: 'instant' });
        } catch {
            window.scrollTo(0, 0);
        }
    }
}

function scheduleVisualViewportCssVars() {
    if (_viewportRafPending) {
        return;
    }
    _viewportRafPending = true;
    requestAnimationFrame(() => {
        _viewportRafPending = false;
        applyVisualViewportCssVars();
    });
}

/**
 * Идемпотентный запуск: один раз на загрузку страницы (импорт из app-loader).
 */
export function initPlatformViewportAppVh() {
    if (typeof window === 'undefined') {
        return;
    }
    if (window.__PLATFORM_VIEWPORT_VH_INIT__) {
        return;
    }
    window.__PLATFORM_VIEWPORT_VH_INIT__ = true;

    const mq = window.matchMedia(MOBILE_SHELL_MQ);
    const onVisualViewport = () => {
        scheduleVisualViewportCssVars();
    };

    mq.addEventListener('change', onVisualViewport);

    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', onVisualViewport);
        window.visualViewport.addEventListener('scroll', onVisualViewport);
    }

    applyVisualViewportCssVars();
}

initPlatformViewportAppVh();

function scheduleCapacitorSplashHide() {
    if (typeof window === 'undefined') {
        return;
    }
    if (
        typeof window.Capacitor === 'undefined' ||
        typeof window.Capacitor.isNativePlatform !== 'function' ||
        !window.Capacitor.isNativePlatform()
    ) {
        return;
    }
    const runHide = () => {
        void import('@capacitor/splash-screen').then(({ SplashScreen }) => SplashScreen.hide());
    };
    const afterPaint = () => {
        requestAnimationFrame(() => {
            requestAnimationFrame(runHide);
        });
    };
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', afterPaint, { once: true });
    } else {
        afterPaint();
    }
}

scheduleCapacitorSplashHide();
