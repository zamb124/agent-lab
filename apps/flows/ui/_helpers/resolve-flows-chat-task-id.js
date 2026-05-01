/**
 * Единый резолв A2A task_id для модалок логов / трейсинга из слайса flows/chat.
 *
 * Порядок: currentTaskId → bucket.taskId для currentContextId → последний непустой
 * taskId у сообщений в корзине текущего контекста (с конца ленты).
 */

import { isPlainObject } from './flows-resolvers.js';

/**
 * @param {unknown} chatState
 * @returns {string}
 */
export function resolveFlowsChatTaskId(chatState) {
    if (!isPlainObject(chatState)) {
        return '';
    }
    const top = chatState.currentTaskId;
    if (typeof top === 'string' && top.length > 0) {
        return top;
    }
    const ctx = chatState.currentContextId;
    if (typeof ctx !== 'string' || ctx.length === 0) {
        return '';
    }
    const buckets = chatState.messagesByContextId;
    if (!isPlainObject(buckets)) {
        return '';
    }
    const bucket = buckets[ctx];
    if (!isPlainObject(bucket)) {
        return '';
    }
    const fromBucket = bucket.taskId;
    if (typeof fromBucket === 'string' && fromBucket.length > 0) {
        return fromBucket;
    }
    const messages = bucket.messages;
    if (!Array.isArray(messages) || messages.length === 0) {
        return '';
    }
    for (let i = messages.length - 1; i >= 0; i -= 1) {
        const m = messages[i];
        if (!isPlainObject(m)) {
            continue;
        }
        const tid = m.taskId;
        if (typeof tid === 'string' && tid.length > 0) {
            return tid;
        }
    }
    return '';
}
