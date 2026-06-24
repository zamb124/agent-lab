/**
 * Персональные prefs панелей свойств редактора flow (localStorage, не flow config).
 *
 * Ключ: platform:flows:editor_property_panel_prefs
 * Форма: { property_panels?: Record<string, { left, top, width, height, collapsed, expandedWidth?, expandedHeight? }> }
 */

import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';

export const FLOWS_EDITOR_PROPERTY_PANEL_PREFS_KEY = platformStorageKey(
    'flows',
    'editor_property_panel_prefs',
);

/** @typedef {{ left: number, top: number, width: number, height: number, collapsed: boolean, expandedWidth?: number, expandedHeight?: number }} PropertyPanelRectPref */

const PERSIST_DEBOUNCE_MS = 300;

/** @type {ReturnType<typeof setTimeout> | null} */
let persistTimer = null;

/** @type {{ panelId: string, rect: PropertyPanelRectPref } | null} */
let pendingRectPref = null;

function _isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/**
 * @returns {{ property_panels?: Record<string, unknown>, property_panel?: Record<string, unknown> }}
 */
function _readRoot() {
    const raw = globalThis.localStorage.getItem(FLOWS_EDITOR_PROPERTY_PANEL_PREFS_KEY);
    if (raw === null) {
        return {};
    }
    let parsed;
    try {
        parsed = JSON.parse(raw);
    } catch (err) {
        throw new Error(
            `flows-editor-property-panel-prefs: invalid JSON in ${FLOWS_EDITOR_PROPERTY_PANEL_PREFS_KEY}`,
            { cause: err },
        );
    }
    if (!_isPlainObject(parsed)) {
        throw new Error(
            `flows-editor-property-panel-prefs: root must be object, got ${typeof parsed}`,
        );
    }
    return parsed;
}

/**
 * @param {{ property_panels?: Record<string, unknown> }} root
 */
function _writeRoot(root) {
    globalThis.localStorage.setItem(FLOWS_EDITOR_PROPERTY_PANEL_PREFS_KEY, JSON.stringify(root));
}

/**
 * @param {unknown} entry
 * @returns {PropertyPanelRectPref | null}
 */
function _normalizePropertyPanelRect(entry) {
    if (!_isPlainObject(entry)) {
        return null;
    }
    const left = Number(entry.left);
    const top = Number(entry.top);
    const width = Number(entry.width);
    const height = Number(entry.height);
    if (!Number.isFinite(left) || !Number.isFinite(top)) {
        return null;
    }
    if (!Number.isFinite(width) || width <= 0 || !Number.isFinite(height) || height <= 0) {
        return null;
    }
    const normalized = {
        left,
        top,
        width,
        height,
        collapsed: entry.collapsed === true,
    };
    const expandedWidth = Number(entry.expandedWidth);
    const expandedHeight = Number(entry.expandedHeight);
    if (Number.isFinite(expandedWidth) && expandedWidth > 0) {
        normalized.expandedWidth = expandedWidth;
    }
    if (Number.isFinite(expandedHeight) && expandedHeight > 0) {
        normalized.expandedHeight = expandedHeight;
    }
    return normalized;
}

/**
 * @param {string} panelId
 * @returns {PropertyPanelRectPref | null}
 */
export function readPropertyPanelRectPref(panelId) {
    if (typeof panelId !== 'string' || panelId.length === 0) {
        throw new Error('readPropertyPanelRectPref: panelId is required');
    }
    const root = _readRoot();
    const panels = root.property_panels;
    if (_isPlainObject(panels) && _isPlainObject(panels[panelId])) {
        const normalized = _normalizePropertyPanelRect(panels[panelId]);
        if (normalized) {
            return normalized;
        }
    }
    if (panelId === '__legacy__' && _isPlainObject(root.property_panel)) {
        return _normalizePropertyPanelRect(root.property_panel);
    }
    return null;
}

/**
 * @param {string} panelId
 * @param {PropertyPanelRectPref} rect
 */
function _flushPropertyPanelRectPref(panelId, rect) {
    const root = _readRoot();
    const panels = _isPlainObject(root.property_panels) ? { ...root.property_panels } : {};
    panels[panelId] = {
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
        collapsed: rect.collapsed,
    };
    if (typeof rect.expandedWidth === 'number' && Number.isFinite(rect.expandedWidth)) {
        panels[panelId].expandedWidth = rect.expandedWidth;
    }
    if (typeof rect.expandedHeight === 'number' && Number.isFinite(rect.expandedHeight)) {
        panels[panelId].expandedHeight = rect.expandedHeight;
    }
    root.property_panels = panels;
    _writeRoot(root);
}

/**
 * @param {string} panelId
 * @param {PropertyPanelRectPref} rect
 */
export function schedulePropertyPanelRectPersist(panelId, rect) {
    if (typeof panelId !== 'string' || panelId.length === 0) {
        throw new Error('schedulePropertyPanelRectPersist: panelId is required');
    }
    if (!_isPlainObject(rect)) {
        throw new Error('schedulePropertyPanelRectPersist: rect must be object');
    }
    const left = Number(rect.left);
    const top = Number(rect.top);
    const width = Number(rect.width);
    const height = Number(rect.height);
    if (!Number.isFinite(left) || !Number.isFinite(top) || !Number.isFinite(width) || !Number.isFinite(height)) {
        throw new Error('schedulePropertyPanelRectPersist: rect numbers required');
    }
    pendingRectPref = {
        panelId,
        rect: {
            left,
            top,
            width,
            height,
            collapsed: rect.collapsed === true,
            expandedWidth: typeof rect.expandedWidth === 'number' ? rect.expandedWidth : undefined,
            expandedHeight: typeof rect.expandedHeight === 'number' ? rect.expandedHeight : undefined,
        },
    };
    if (persistTimer !== null) {
        clearTimeout(persistTimer);
    }
    persistTimer = setTimeout(() => {
        persistTimer = null;
        const batch = pendingRectPref;
        pendingRectPref = null;
        if (!batch) {
            return;
        }
        _flushPropertyPanelRectPref(batch.panelId, batch.rect);
    }, PERSIST_DEBOUNCE_MS);
}

/**
 * @param {string} panelId
 * @param {PropertyPanelRectPref} rect
 */
export function writePropertyPanelRectPref(panelId, rect) {
    if (typeof panelId !== 'string' || panelId.length === 0) {
        throw new Error('writePropertyPanelRectPref: panelId is required');
    }
    if (!_isPlainObject(rect)) {
        throw new Error('writePropertyPanelRectPref: rect must be object');
    }
    const left = Number(rect.left);
    const top = Number(rect.top);
    const width = Number(rect.width);
    const height = Number(rect.height);
    if (!Number.isFinite(left) || !Number.isFinite(top) || !Number.isFinite(width) || !Number.isFinite(height)) {
        throw new Error('writePropertyPanelRectPref: rect numbers required');
    }
    if (persistTimer !== null) {
        clearTimeout(persistTimer);
        persistTimer = null;
    }
    pendingRectPref = null;
    _flushPropertyPanelRectPref(panelId, {
        left,
        top,
        width,
        height,
        collapsed: rect.collapsed === true,
        expandedWidth: typeof rect.expandedWidth === 'number' ? rect.expandedWidth : undefined,
        expandedHeight: typeof rect.expandedHeight === 'number' ? rect.expandedHeight : undefined,
    });
}
