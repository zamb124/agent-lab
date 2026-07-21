/**
 * Одна страница GET /flows/api/v1/tools/all — page size ≤ TOOLS_ALL_PAGE_LIMIT.
 */

import { isPlainObject } from './flows-resolvers.js';

/** Максимум `limit` на один HTTP-запрос tools/all (API + клиент). */
export const TOOLS_ALL_PAGE_LIMIT = 20;

/**
 * @typedef {{ items: Record<string, unknown>[], total: number, limit: number, offset: number, hasMore: boolean }} ToolsAllPage
 */

/**
 * @param {(payload: { limit: number, offset: number, picker_category?: string, q?: string }) => Promise<unknown>} runOp
 * @param {{ offset?: number, picker_category?: string, q?: string }} [opts]
 * @returns {Promise<ToolsAllPage>}
 */
export async function fetchToolsAllPage(runOp, opts = {}) {
    if (typeof runOp !== 'function') {
        throw new Error('fetchToolsAllPage: runOp required');
    }
    const offset = typeof opts.offset === 'number' && opts.offset >= 0 ? opts.offset : 0;
    /** @type {{ limit: number, offset: number, picker_category?: string, q?: string }} */
    const payload = { limit: TOOLS_ALL_PAGE_LIMIT, offset };
    if (typeof opts.picker_category === 'string' && opts.picker_category.length > 0) {
        payload.picker_category = opts.picker_category;
    }
    if (typeof opts.q === 'string' && opts.q.trim().length > 0) {
        payload.q = opts.q.trim();
    }
    const result = await runOp(payload);
    if (result === null || !isPlainObject(result) || !Array.isArray(result.items)) {
        throw new Error('fetchToolsAllPage: tools_all page failed');
    }
    /** @type {Record<string, unknown>[]} */
    const items = [];
    for (const item of result.items) {
        if (isPlainObject(item)) {
            items.push(item);
        }
    }
    const total = typeof result.total === 'number' ? result.total : offset + items.length;
    const nextOffset = offset + items.length;
    return {
        items,
        total,
        limit: TOOLS_ALL_PAGE_LIMIT,
        offset,
        hasMore: items.length > 0 && nextOffset < total,
    };
}
