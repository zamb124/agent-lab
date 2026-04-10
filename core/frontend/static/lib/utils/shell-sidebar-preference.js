/**
 * Глобальное (на профиль браузера) состояние свёрнутости shell-sidebar desktop-режима.
 * Один ключ для всех SPA-сервисов; запись — из PlatformServiceSidebar при collapse-change.
 */

export const SHELL_SIDEBAR_COLLAPSED_STORAGE_KEY = 'platform:shell-sidebar-collapsed';

/**
 * @returns {boolean}
 */
export function readShellSidebarCollapsed() {
    const raw = window.localStorage.getItem(SHELL_SIDEBAR_COLLAPSED_STORAGE_KEY);
    if (raw === null) {
        return false;
    }
    if (raw === 'true') {
        return true;
    }
    if (raw === 'false') {
        return false;
    }
    throw new Error(`readShellSidebarCollapsed: invalid stored value ${JSON.stringify(raw)}`);
}

/**
 * @param {boolean} collapsed
 */
export function writeShellSidebarCollapsed(collapsed) {
    if (typeof collapsed !== 'boolean') {
        throw new Error('writeShellSidebarCollapsed: expected boolean');
    }
    window.localStorage.setItem(SHELL_SIDEBAR_COLLAPSED_STORAGE_KEY, collapsed ? 'true' : 'false');
}
