/**
 * Одна страница GET /flows/api/v1/tools/all — page size ≤ TOOLS_ALL_PAGE_LIMIT.
 * Tag-groups: отдельный OffsetPage-лимит (лёгкие записи описаний).
 */

import { isPlainObject } from './flows-resolvers.js';

/** Максимум `limit` на один HTTP-запрос tools/all (API + клиент). */
export const TOOLS_ALL_PAGE_LIMIT = 20;

/** Максимум `limit` для GET /flows/api/v1/tools/tag-groups. */
export const TAG_GROUPS_PAGE_LIMIT = 200;

/**
 * @typedef {{ items: Record<string, unknown>[], total: number, limit: number, offset: number, hasMore: boolean }} ToolsAllPage
 */

/**
 * @param {(payload: { limit: number, offset: number, picker_category?: string, q?: string }) => Promise<unknown>} runOp
 * @param {{ offset?: number, picker_category?: string, q?: string }} [opts]
 * @returns {Promise<ToolsAllPage>}
 */
export async function fetchToolsAllPage(
    runOp: (payload: {
        limit: number;
        offset: number;
        picker_category?: string;
        q?: string;
    }) => Promise<unknown>,
    opts: { offset?: number; picker_category?: string; q?: string } = {},
) {
    if (typeof runOp !== 'function') {
        throw new Error('fetchToolsAllPage: runOp required');
    }
    const offsetValue = opts.offset;
    const offset = typeof offsetValue === 'number' && offsetValue >= 0 ? offsetValue : 0;
    const payload: { limit: number; offset: number; picker_category?: string; q?: string } = {
        limit: TOOLS_ALL_PAGE_LIMIT,
        offset,
    };
    const category = opts.picker_category;
    if (typeof category === 'string' && category.length > 0) {
        payload.picker_category = category;
    }
    const query = opts.q;
    if (typeof query === 'string' && query.trim().length > 0) {
        payload.q = query.trim();
    }
    const result = await runOp(payload);
    if (result === null || !isPlainObject(result) || !Array.isArray(result.items)) {
        throw new Error('fetchToolsAllPage: tools_all lastResult.items must be an array');
    }
    if (typeof result.total !== 'number') {
        throw new Error('fetchToolsAllPage: tools_all lastResult.total must be a number');
    }
    /** @type {Record<string, unknown>[]} */
    const items = [];
    for (const item of result.items) {
        if (!isPlainObject(item)) {
            throw new Error('fetchToolsAllPage: tools_all item must be an object');
        }
        items.push(item);
    }
    const total = result.total;
    const nextOffset = offset + items.length;
    return {
        items,
        total,
        limit: TOOLS_ALL_PAGE_LIMIT,
        offset,
        hasMore: items.length > 0 && nextOffset < total,
    };
}
