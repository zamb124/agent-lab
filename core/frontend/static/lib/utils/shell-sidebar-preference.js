/**
 * Глобальное (на профиль браузера) состояние свёрнутости shell-sidebar desktop-режима.
 * Один ключ для всех SPA-сервисов; запись — из PlatformServiceSidebar при collapse-change.
 */

import { platformStorageKey } from './storage-keys.js';
import { storageGet, storageSet } from './platform-storage.js';

export const SHELL_SIDEBAR_COLLAPSED_STORAGE_KEY = platformStorageKey('core', 'shell_sidebar_collapsed');

/**
 * @returns {boolean}
 */
export function readShellSidebarCollapsed() {
    const raw = storageGet(SHELL_SIDEBAR_COLLAPSED_STORAGE_KEY);
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
    storageSet(SHELL_SIDEBAR_COLLAPSED_STORAGE_KEY, collapsed ? 'true' : 'false');
}
