/**
 * Персистентность масштаба и смещения mind map в localStorage — по корневой сущности
 * и режиму (полный экран vs компактная вкладка карточки).
 */

import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import { storageGet, storageSetJson } from '@platform/lib/utils/platform-storage.js';

function _segment(raw) {
    return String(raw).trim().toLowerCase().replace(/[^a-z0-9_]+/g, '_');
}

const MIN_ZOOM = 0.12;
const MAX_ZOOM = 4;

/**
 * @param {string} rootEntityId
 * @param {boolean} compact
 * @returns {string}
 */
export function buildMindmapViewStorageKey(rootEntityId, compact) {
    if (typeof rootEntityId !== 'string' || rootEntityId.trim().length === 0) {
        throw new Error('mindmap-view-preference: rootEntityId must be non-empty string');
    }
    const id = rootEntityId.trim();
    const scope = compact === true ? 'c' : 'f';
    return platformStorageKey('crm', `mindmap_view.v1.${_segment(id)}.${scope}`);
}

/**
 * @param {unknown} n
 * @returns {boolean}
 */
function _isFiniteNumber(n) {
    return typeof n === 'number' && Number.isFinite(n);
}

/**
 * @param {string} rootEntityId
 * @param {boolean} compact
 * @returns {{ zoom: number, panUx: number, panUy: number } | null}
 */
export function readMindmapView(rootEntityId, compact) {
    const key = buildMindmapViewStorageKey(rootEntityId, compact);
    const raw = storageGet(key);
    if (raw === null) {
        return null;
    }
    let parsed;
    try {
        parsed = JSON.parse(raw);
    } catch (e) {
        throw new Error(
            `readMindmapView: invalid JSON for ${JSON.stringify(key)}: ${e instanceof Error ? e.message : String(e)}`,
        );
    }
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error(`readMindmapView: expected object at ${JSON.stringify(key)}`);
    }
    if (!Object.prototype.hasOwnProperty.call(parsed, 'zoom')) {
        throw new Error(`readMindmapView: missing zoom at ${JSON.stringify(key)}`);
    }
    if (!Object.prototype.hasOwnProperty.call(parsed, 'panUx')) {
        throw new Error(`readMindmapView: missing panUx at ${JSON.stringify(key)}`);
    }
    if (!Object.prototype.hasOwnProperty.call(parsed, 'panUy')) {
        throw new Error(`readMindmapView: missing panUy at ${JSON.stringify(key)}`);
    }
    const zoom = parsed.zoom;
    const panUx = parsed.panUx;
    const panUy = parsed.panUy;
    if (!_isFiniteNumber(zoom) || zoom < MIN_ZOOM || zoom > MAX_ZOOM) {
        throw new Error(`readMindmapView: zoom out of range at ${JSON.stringify(key)}`);
    }
    if (!_isFiniteNumber(panUx) || !_isFiniteNumber(panUy)) {
        throw new Error(`readMindmapView: pan must be finite numbers at ${JSON.stringify(key)}`);
    }
    return { zoom, panUx, panUy };
}

/**
 * @param {string} rootEntityId
 * @param {boolean} compact
 * @param {{ zoom: number, panUx: number, panUy: number }} view
 */
export function writeMindmapView(rootEntityId, compact, view) {
    const key = buildMindmapViewStorageKey(rootEntityId, compact);
    if (view === null || typeof view !== 'object' || Array.isArray(view)) {
        throw new Error('writeMindmapView: view must be a plain object');
    }
    if (!_isFiniteNumber(view.zoom) || view.zoom < MIN_ZOOM || view.zoom > MAX_ZOOM) {
        throw new Error('writeMindmapView: zoom out of range');
    }
    if (!_isFiniteNumber(view.panUx) || !_isFiniteNumber(view.panUy)) {
        throw new Error('writeMindmapView: pan must be finite numbers');
    }
    const payload = {
        zoom: view.zoom,
        panUx: view.panUx,
        panUy: view.panUy,
    };
    storageSetJson(key, payload);
}
