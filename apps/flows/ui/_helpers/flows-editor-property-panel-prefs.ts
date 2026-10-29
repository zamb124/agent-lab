/**
 * Персональные prefs панелей свойств редактора flow (localStorage, не flow config).
 *
 * Ключ: platform:flows:editor_property_panel_prefs
 * Форма: {
 *   property_panels?: Record<string, { left, top, width, height, collapsed, expandedWidth?, expandedHeight? }>,
 *   assistant_width?: number,
 * }
 */

import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import { storageGet, storageSetJson } from '@platform/lib/utils/platform-storage.js';

export const FLOWS_EDITOR_PROPERTY_PANEL_PREFS_KEY = platformStorageKey(
    'flows',
    'editor_property_panel_prefs',
);

export const ASSISTANT_COL_WIDTH_DEFAULT = 380;
export const ASSISTANT_COL_WIDTH_MIN = 280;
export const ASSISTANT_COL_WIDTH_MAX = 640;

export interface PropertyPanelRectPref {
    left: number;
    top: number;
    width: number;
    height: number;
    collapsed: boolean;
    expandedWidth?: number;
    expandedHeight?: number;
}

interface PendingRectPref {
    panelId: string;
    rect: PropertyPanelRectPref;
}

const PERSIST_DEBOUNCE_MS = 300;

/** @type {ReturnType<typeof setTimeout> | null} */
let persistTimer: ReturnType<typeof setTimeout> | null = null;

let pendingRectPref: PendingRectPref | null = null;

/** @type {ReturnType<typeof setTimeout> | null} */
let assistantWidthPersistTimer: ReturnType<typeof setTimeout> | null = null;

/** @type {number | null} */
let pendingAssistantWidth: number | null = null;

function _isPlainObject(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/**
 * @param {unknown} value
 * @returns {number | null}
 */
export function normalizeAssistantWidth(value: unknown) {
    const width = Number(value);
    if (!Number.isFinite(width)) {
        return null;
    }
    return Math.min(ASSISTANT_COL_WIDTH_MAX, Math.max(ASSISTANT_COL_WIDTH_MIN, Math.round(width)));
}

/**
 * @returns {{ property_panels?: Record<string, unknown>, property_panel?: Record<string, unknown>, assistant_width?: unknown }}
 */
function _readRoot(): Record<string, unknown> {
    const raw = storageGet(FLOWS_EDITOR_PROPERTY_PANEL_PREFS_KEY);
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
 * @param {{ property_panels?: Record<string, unknown>, assistant_width?: number }} root
 */
function _writeRoot(root: Record<string, unknown>) {
    storageSetJson(FLOWS_EDITOR_PROPERTY_PANEL_PREFS_KEY, root);
}

/**
 * @param {unknown} entry
 * @returns {PropertyPanelRectPref | null}
 */
function _normalizePropertyPanelRect(entry: unknown): PropertyPanelRectPref | null {
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
    const normalized: PropertyPanelRectPref = {
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
export function readPropertyPanelRectPref(panelId: unknown): PropertyPanelRectPref | null {
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
 * @returns {number | null}
 */
export function readAssistantWidthPref() {
    const root = _readRoot();
    return normalizeAssistantWidth(root.assistant_width);
}

/**
 * @param {number} width
 */
function _flushAssistantWidthPref(width: unknown) {
    const normalized = normalizeAssistantWidth(width);
    if (normalized === null) {
        throw new Error('writeAssistantWidthPref: width must be a finite number');
    }
    const root = _readRoot();
    root.assistant_width = normalized;
    _writeRoot(root);
}

/**
 * @param {number} width
 */
export function scheduleAssistantWidthPersist(width: unknown) {
    const normalized = normalizeAssistantWidth(width);
    if (normalized === null) {
        throw new Error('scheduleAssistantWidthPersist: width must be a finite number');
    }
    pendingAssistantWidth = normalized;
    if (assistantWidthPersistTimer !== null) {
        clearTimeout(assistantWidthPersistTimer);
    }
    assistantWidthPersistTimer = setTimeout(() => {
        assistantWidthPersistTimer = null;
        const batch = pendingAssistantWidth;
        pendingAssistantWidth = null;
        if (batch === null) {
            return;
        }
        _flushAssistantWidthPref(batch);
    }, PERSIST_DEBOUNCE_MS);
}

/**
 * @param {number} width
 */
export function writeAssistantWidthPref(width: unknown) {
    if (assistantWidthPersistTimer !== null) {
        clearTimeout(assistantWidthPersistTimer);
        assistantWidthPersistTimer = null;
    }
    pendingAssistantWidth = null;
    _flushAssistantWidthPref(width);
}

/**
 * @param {string} panelId
 * @param {PropertyPanelRectPref} rect
 */
function _flushPropertyPanelRectPref(panelId: string, rect: PropertyPanelRectPref) {
    const root = _readRoot();
    const panels: Record<string, unknown> = _isPlainObject(root.property_panels) ? { ...root.property_panels } : {};
    const stored: PropertyPanelRectPref = {
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
        collapsed: rect.collapsed,
    };
    if (typeof rect.expandedWidth === 'number' && Number.isFinite(rect.expandedWidth)) {
        stored.expandedWidth = rect.expandedWidth;
    }
    if (typeof rect.expandedHeight === 'number' && Number.isFinite(rect.expandedHeight)) {
        stored.expandedHeight = rect.expandedHeight;
    }
    panels[panelId] = stored;
    root.property_panels = panels;
    _writeRoot(root);
}

/**
 * @param {string} panelId
 * @param {PropertyPanelRectPref} rect
 */
export function schedulePropertyPanelRectPersist(panelId: unknown, rect: unknown) {
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
export function writePropertyPanelRectPref(panelId: unknown, rect: unknown) {
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
