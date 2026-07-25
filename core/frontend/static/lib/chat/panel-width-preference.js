import { platformStorageKey } from '../utils/storage-keys.js';

export const LARA_PANEL_WIDTH_MIN_PX = 320;
export const LARA_PANEL_WIDTH_MAX_CAP_PX = 960;

const WIDTH_KEY_PREFIX = 'lara_panel_width';

function _storageKey(scope, branchId) {
    if (typeof branchId !== 'string' || !/^[a-z][a-z0-9_]*$/.test(branchId)) {
        throw new Error('Lara panel width branchId must be lowercase snake_case');
    }
    return platformStorageKey(scope, `${WIDTH_KEY_PREFIX}.${branchId}`);
}

function _validateWidth(value) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < LARA_PANEL_WIDTH_MIN_PX) {
        throw new Error(
            `Lara panel width must be a finite number >= ${LARA_PANEL_WIDTH_MIN_PX}`,
        );
    }
    return value;
}

/**
 * @param {string} scope
 * @param {string} branchId
 * @returns {number | null}
 */
export function readLaraPanelWidth(scope, branchId) {
    if (typeof window === 'undefined') {
        return null;
    }
    const serialized = window.localStorage.getItem(_storageKey(scope, branchId));
    if (serialized === null) {
        return null;
    }
    const parsed = JSON.parse(serialized);
    if (typeof parsed !== 'number') {
        throw new Error('Lara panel width must be a JSON number');
    }
    return _validateWidth(parsed);
}

/**
 * @param {string} scope
 * @param {string} branchId
 * @param {number} widthPx
 */
export function writeLaraPanelWidth(scope, branchId, widthPx) {
    if (typeof window === 'undefined') {
        return;
    }
    const normalized = _validateWidth(widthPx);
    window.localStorage.setItem(_storageKey(scope, branchId), JSON.stringify(normalized));
}

/**
 * @param {number} widthPx
 * @param {number} viewportWidth
 * @returns {number}
 */
export function clampLaraPanelWidth(widthPx, viewportWidth) {
    if (typeof widthPx !== 'number' || !Number.isFinite(widthPx)) {
        throw new Error('clampLaraPanelWidth: widthPx must be a finite number');
    }
    if (typeof viewportWidth !== 'number' || !Number.isFinite(viewportWidth) || viewportWidth <= 0) {
        throw new Error('clampLaraPanelWidth: viewportWidth must be a positive finite number');
    }
    const maxWidth = Math.min(LARA_PANEL_WIDTH_MAX_CAP_PX, Math.max(LARA_PANEL_WIDTH_MIN_PX, viewportWidth - 24));
    return Math.min(Math.max(widthPx, LARA_PANEL_WIDTH_MIN_PX), maxWidth);
}
