/**
 * Platform tool tag group descriptions (LLM) for tool picker.
 * REST: GET /flows/api/v1/tools/tag-groups
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const toolTagGroupsOp = createAsyncOp({
    name: 'flows/tool_tag_groups',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/tools/tag_groups_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/tools/tag-groups' },
});
