/**
 * Office Company Members — участники активной компании.
 *
 * Backend: GET /documents/api/v1/company-members → ListResponse[TeamMemberResponse].
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const companyMembersOp = createAsyncOp({
    name: 'office/company_members',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/company_members/list_requested',
    restMirror: { method: 'GET', path: '/documents/api/v1/company-members' },
});
