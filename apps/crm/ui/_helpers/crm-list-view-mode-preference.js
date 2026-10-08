/**
 * Персистентность ракурса списков CRM в localStorage.
 */

import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import { storageGet, storageSet } from '@platform/lib/utils/platform-storage.js';

const KEYS = Object.freeze({
    entities: platformStorageKey('crm', 'entities.view_mode'),
});

const ALLOWED = Object.freeze({
    entities: new Set(['cards', 'table']),
});

function _key(scope) {
    if (!Object.prototype.hasOwnProperty.call(KEYS, scope)) {
        throw new Error(`crm-list-view-mode-preference: unknown scope "${scope}"`);
    }
    return KEYS[scope];
}

function _allowed(scope) {
    if (!Object.prototype.hasOwnProperty.call(ALLOWED, scope)) {
        throw new Error(`crm-list-view-mode-preference: unknown scope "${scope}"`);
    }
    return ALLOWED[scope];
}

export function readCrmListViewMode(scope, fallback) {
    const allowed = _allowed(scope);
    if (!allowed.has(fallback)) {
        throw new Error('readCrmListViewMode: fallback is not allowed for scope');
    }
    if (typeof window === 'undefined' || !window.localStorage) {
        return fallback;
    }
    const raw = storageGet(_key(scope));
    if (raw === null) return fallback;
    return allowed.has(raw) ? raw : fallback;
}

export function writeCrmListViewMode(scope, mode) {
    const allowed = _allowed(scope);
    if (!allowed.has(mode)) {
        throw new Error('writeCrmListViewMode: mode is not allowed for scope');
    }
    if (typeof window === 'undefined' || !window.localStorage) {
        return;
    }
    storageSet(_key(scope), mode);
}
