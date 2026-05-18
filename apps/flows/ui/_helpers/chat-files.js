import { asArray, asString, isPlainObject } from './flows-resolvers.js';

function stableFileKey(file) {
    if (!isPlainObject(file)) {
        return '';
    }
    const fid = asString(file.file_id);
    const path = asString(file.path) || asString(file.url);
    return fid || path || asString(file.name);
}

/**
 * Collects files for the active chat context from the canonical files bucket,
 * message-local files, and legacy fileIds.
 *
 * @param {object | null | undefined} chatState
 * @param {unknown[]} messages
 * @returns {object[]}
 */
export function collectCurrentChatFiles(chatState, messages) {
    const byKey = new Map();
    const state = isPlainObject(chatState) ? chatState : {};
    const ctx = typeof state.currentContextId === 'string' ? state.currentContextId : '';
    const filesByContext = isPlainObject(state.filesByContextId)
        ? state.filesByContextId
        : null;
    const stateFiles = ctx && filesByContext !== null && Array.isArray(filesByContext[ctx])
        ? filesByContext[ctx]
        : [];

    for (const file of stateFiles) {
        const key = stableFileKey(file);
        if (key.length > 0) {
            byKey.set(key, file);
        }
    }

    for (const message of asArray(messages)) {
        for (const file of asArray(message?.files)) {
            if (!isPlainObject(file)) {
                continue;
            }
            const key = stableFileKey(file);
            if (key.length > 0) {
                byKey.set(key, { ...(byKey.get(key) || {}), ...file });
            }
        }
        for (const rawId of asArray(message?.fileIds)) {
            const fid = asString(rawId);
            if (fid.length === 0 || byKey.has(fid)) {
                continue;
            }
            const path = `/flows/api/v1/files/download/${encodeURIComponent(fid)}`;
            byKey.set(fid, {
                file_id: fid,
                name: fid,
                path,
                url: path,
            });
        }
    }

    return Array.from(byKey.values());
}
