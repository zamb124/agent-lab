/**
 * На узкой ширине (как у мобильного shell) подставляет --app-vh / --app-vw из visualViewport,
 * чтобы fixed-layout и 100%-высота совпадали с видимой областью iOS Safari при съезжающих панелях.
 */

import { installNativeAppShellLinkCapture, installNativeAppShellWindowOpenPatch } from './native-app-shell.js';

installNativeAppShellLinkCapture();
installNativeAppShellWindowOpenPatch();

const MOBILE_SHELL_MQ = '(max-width: 767px)';

function applyVisualViewportCssVars() {
    const root = document.documentElement;
    const mq = window.matchMedia(MOBILE_SHELL_MQ);
    if (!mq.matches) {
        root.style.removeProperty('--app-vh');
        root.style.removeProperty('--app-vw');
        return;
    }
    const vv = window.visualViewport;
    if (!vv || typeof vv.height !== 'number') {
        root.style.removeProperty('--app-vh');
        root.style.removeProperty('--app-vw');
        return;
    }
    root.style.setProperty('--app-vh', `${Math.round(vv.height)}px`);
    root.style.setProperty('--app-vw', `${Math.round(vv.width)}px`);
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
        applyVisualViewportCssVars();
    };

    mq.addEventListener('change', onVisualViewport);

    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', onVisualViewport);
    }

    applyVisualViewportCssVars();
}

initPlatformViewportAppVh();
