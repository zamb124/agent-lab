import { platformStorageKey } from '../../utils/storage-keys.js';
import { parseStoredGeometry, toStoredGeometry } from './drawer-geometry.js';

function _segment(raw) {
    return String(raw).trim().toLowerCase().replace(/[^a-z0-9_]+/g, '_');
}

function _prefsKey(scope) {
    return platformStorageKey('core', `flow_ui.preferences.${_segment(scope)}`);
}
const EMBED_GEOMETRY_FIELD = 'geometry';
const BRANCH_ID_RE = /^[a-z][a-z0-9_]*$/;

function store() {
    try {
        return localStorage;
    } catch {
        return null;
    }
}

function requireNonEmptyString(value, label) {
    if (typeof value !== 'string' || value.trim() === '') {
        throw new Error(`flow-ui-drawer: ${label} must be a non-empty string`);
    }
    return value.trim();
}

export function drawerGeometryStorageKey(branchId) {
    const id = requireNonEmptyString(branchId, 'branchId');
    if (!BRANCH_ID_RE.test(id)) {
        throw new Error('flow-ui-drawer: branchId must be lowercase snake_case');
    }
    return platformStorageKey('core', `assistant.drawer.${id}`);
}

export function readLaraDrawerGeometry(branchId) {
    const storage = store();
    if (storage === null) {
        return null;
    }
    const raw = storage.getItem(drawerGeometryStorageKey(branchId));
    if (raw === null) {
        return null;
    }
    return parseStoredGeometry(JSON.parse(raw));
}

export function writeLaraDrawerGeometry(branchId, geometry) {
    const storage = store();
    if (storage === null) {
        throw new Error('flow-ui preferences: localStorage unavailable');
    }
    storage.setItem(
        drawerGeometryStorageKey(branchId),
        JSON.stringify(toStoredGeometry(geometry)),
    );
}

export function readEmbedDrawerGeometry(embedId) {
    const id = requireNonEmptyString(embedId, 'embedId');
    const prefs = readFlowUIPreferences(`drawer:${id}`);
    if (!Object.prototype.hasOwnProperty.call(prefs, EMBED_GEOMETRY_FIELD)) {
        return null;
    }
    return parseStoredGeometry(prefs[EMBED_GEOMETRY_FIELD]);
}

export function writeEmbedDrawerGeometry(embedId, geometry) {
    const id = requireNonEmptyString(embedId, 'embedId');
    writeFlowUIPreferences(`drawer:${id}`, {
        [EMBED_GEOMETRY_FIELD]: toStoredGeometry(geometry),
    });
}

export function readFlowUIPreferences(scope = 'global') {
    const storage = store();
    if (!storage) return {};
    const raw = storage.getItem(_prefsKey(scope));
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('flow-ui preferences: invalid stored JSON object');
    }
    return parsed;
}

export function writeFlowUIPreferences(scope, patch) {
    const storage = store();
    if (!storage) {
        throw new Error('flow-ui preferences: localStorage unavailable');
    }
    if (!patch || typeof patch !== 'object' || Array.isArray(patch)) {
        throw new Error('flow-ui preferences: patch object required');
    }
    storage.setItem(
        _prefsKey(scope),
        JSON.stringify({ ...readFlowUIPreferences(scope), ...patch }),
    );
}

/** Shared toggle event for Lara / platform assistant drawer hosts. */
export const PLATFORM_LARA_TOGGLE_EVENT = 'platform-lara-open';
export const FLOW_UI_TOGGLE_EVENT = PLATFORM_LARA_TOGGLE_EVENT;

export function dispatchFlowUIWindowToggle(eventName, detail) {
    if (typeof eventName !== 'string' || eventName.length === 0) {
        throw new Error('dispatchFlowUIWindowToggle: eventName must be non-empty string');
    }
    if (typeof globalThis.dispatchEvent !== 'function') {
        throw new Error('dispatchFlowUIWindowToggle: globalThis.dispatchEvent unavailable');
    }
    const payload = typeof detail === 'object' && detail !== null ? detail : {};
    globalThis.dispatchEvent(new CustomEvent(eventName, { detail: payload }));
}

export function openPlatformLaraAssistant() {
    dispatchFlowUIWindowToggle(PLATFORM_LARA_TOGGLE_EVENT, { open: true });
}
