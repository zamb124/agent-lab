/**
 * Персистентность свёрнутых групп platform-sidebar-nav-tree (по scope).
 * В storage только пары id -> false (явно свёрнута); отсутствие ключа у группы = развёрнута.
 */

import { isPlainRecord } from '../events/payload.js';
import { platformStorageKey } from './storage-keys.js';
import { storageGet, storageSetJson } from './platform-storage.js';
function _segment(raw: unknown): string {
    return String(raw).trim().toLowerCase().replace(/[^a-z0-9_]+/g, '_');
}

/**
 * @param {string} scope
 * @returns {string}
 */
function _storageKey(scope: string): string {
    if (typeof scope !== 'string' || scope.trim().length === 0) {
        throw new Error('sidebar-nav-tree preference: scope must be non-empty string');
    }
    return platformStorageKey('core', `sidebar_nav_tree.${_segment(scope)}`);
}

/**
 * @param {string} scope
 * @returns {Record<string, boolean>}
 */
export function readSidebarNavTreeExpanded(scope: string): Record<string, boolean> {
    const key = _storageKey(scope);
    const raw = storageGet(key);
    if (raw === null) {
        return Object.create(null);
    }
    let parsed: unknown;
    try {
        parsed = JSON.parse(raw);
    } catch (e) {
        throw new Error(
            `readSidebarNavTreeExpanded: invalid JSON for ${JSON.stringify(key)}: ${e instanceof Error ? e.message : String(e)}`,
        );
    }
    if (!isPlainRecord(parsed)) {
        throw new Error(`readSidebarNavTreeExpanded: expected object at ${JSON.stringify(key)}`);
    }
    const out: Record<string, boolean> = Object.create(null);
    for (const k of Object.keys(parsed)) {
        if (typeof k !== 'string') {
            throw new Error(`readSidebarNavTreeExpanded: key must be string at ${JSON.stringify(key)}`);
        }
        const v = parsed[k];
        if (v === false) {
            out[k] = false;
            continue;
        }
        if (v === true) {
            throw new Error(
                `readSidebarNavTreeExpanded: only false values allowed in storage, got true for ${JSON.stringify(k)}`,
            );
        }
        throw new Error(
            `readSidebarNavTreeExpanded: value for ${JSON.stringify(k)} must be boolean false, got ${typeof v}`,
        );
    }
    return out;
}

/**
 * Сохранять только свёрнутые группы (id -> false). Остальные ключи из expandedById игнорируются.
 *
 * @param {string} scope
 * @param {Record<string, boolean>} expandedById
 */
export function writeSidebarNavTreeExpanded(scope: string, expandedById: Record<string, boolean | undefined>): void {
    const key = _storageKey(scope);
    if (expandedById === null || typeof expandedById !== 'object' || Array.isArray(expandedById)) {
        throw new Error('writeSidebarNavTreeExpanded: expandedById must be a plain object');
    }
    const compact: Record<string, boolean> = Object.create(null);
    for (const id of Object.keys(expandedById)) {
        if (typeof id !== 'string') {
            throw new Error('writeSidebarNavTreeExpanded: keys must be strings');
        }
        const v = expandedById[id];
        if (v === false) {
            compact[id] = false;
            continue;
        }
        if (v === true || v === undefined) {
            continue;
        }
        throw new Error(`writeSidebarNavTreeExpanded: value for ${JSON.stringify(id)} must be true, false, or absent`);
    }
    storageSetJson(key, compact);
}
