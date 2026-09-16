import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';

const DRAFTS_STORAGE_KEY = platformStorageKey('flows', 'interface_drafts');

export function stableStringify(value) {
    if (value === null || typeof value !== 'object') return JSON.stringify(value);
    if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`;
}

export function readDrafts() {
    const raw = globalThis.localStorage.getItem(DRAFTS_STORAGE_KEY);
    return raw === null ? {} : JSON.parse(raw);
}

export function writeDraft(documentKey, document) {
    const drafts = readDrafts();
    if (document === null) delete drafts[documentKey];
    else drafts[documentKey] = document;
    globalThis.localStorage.setItem(DRAFTS_STORAGE_KEY, JSON.stringify(drafts));
}

export function clearStoredInterfaceDraft(documentKey) {
    writeDraft(documentKey, null);
}
