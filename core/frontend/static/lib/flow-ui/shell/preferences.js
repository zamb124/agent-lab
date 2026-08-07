const PREFIX = 'linnex.flow-ui.preferences.v1';

function store() {
    try {
        return localStorage;
    } catch {
        return null;
    }
}

export function readFlowUIPreferences(scope = 'global') {
    const storage = store();
    if (!storage) return {};
    const raw = storage.getItem(`${PREFIX}:${scope}`);
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
        `${PREFIX}:${scope}`,
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

export function toggleLinnexFlowUI(detail = {}) {
    dispatchFlowUIWindowToggle(FLOW_UI_TOGGLE_EVENT, detail);
}

export function openPlatformLaraAssistant() {
    dispatchFlowUIWindowToggle(PLATFORM_LARA_TOGGLE_EVENT, { open: true });
}
