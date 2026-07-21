/**
 * Platform tool tag group descriptions (LLM) for tool picker.
 * REST: GET /flows/api/v1/tools/tag-groups
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { TOOLS_ALL_PAGE_LIMIT } from '../../_helpers/flows-tools-all-pages.js';

export const toolTagGroupsOp = createAsyncOp({
    name: 'flows/tool_tag_groups',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/tools/tag-groups' },
    request: async ({ payload }) => {
        const src = payload && typeof payload === 'object' ? payload : {};
        const limit = typeof src.limit === 'number' && src.limit > 0
            ? src.limit
            : TOOLS_ALL_PAGE_LIMIT;
        if (limit > TOOLS_ALL_PAGE_LIMIT) {
            throw new Error(
                `flows/tool_tag_groups: limit must be <= ${TOOLS_ALL_PAGE_LIMIT}, got ${limit}`,
            );
        }
        const offset = typeof src.offset === 'number' && src.offset >= 0 ? src.offset : 0;
        const q = new URLSearchParams();
        q.set('limit', String(limit));
        q.set('offset', String(offset));
        return httpRequest({
            method: 'GET',
            url: `/flows/api/v1/tools/tag-groups?${q.toString()}`,
        });
    },
});
