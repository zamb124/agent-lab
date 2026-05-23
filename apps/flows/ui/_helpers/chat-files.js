import { asArray, asString, isPlainObject } from './flows-resolvers.js';

function stableFileKey(file) {
    if (!isPlainObject(file)) {
        return '';
    }
    const fid = asString(file.file_id);
    const url = asString(file.url);
    return fid || url || asString(file.original_name);
}

/**
 * Собирает файлы активного chat-контекста из канонического bucket-а файлов,
 * локальных файлов сообщения.
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
    }

    return Array.from(byKey.values());
}
