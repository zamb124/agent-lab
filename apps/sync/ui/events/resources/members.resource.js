/**
 * Sync Company Members — список участников компании для DM-секции и поиска.
 *
 * `transport: 'http'` — список меняется редко, инициируется один раз при
 * монтировании sidebar. REST-эндпоинт `apps/sync/api/company.py:GET /company/members`.
 *
 * sharedChannelsOp — отдельный AsyncOp для модалки DM-выбора (общие каналы
 * с конкретным участником).
 */

import { createAsyncOp, createResourceCollection } from '@platform/lib/events/index.js';

function _normalizeMember(member) {
    if (!member || typeof member !== 'object') return member;
    return Object.freeze({
        ...member,
        is_online: typeof member.is_online === 'boolean' ? member.is_online : false,
        last_seen_at: typeof member.last_seen_at === 'string' && member.last_seen_at !== ''
            ? member.last_seen_at
            : null,
        name: typeof member.name === 'string' ? member.name : '',
    });
}

export const companyMembersResource = createResourceCollection({
    name: 'sync/company_members',
    baseUrl: '/sync/api/v1/company/members',
    idField: 'user_id',
    operations: ['list'],
    transport: 'http',
    mapItem: _normalizeMember,
});

export const sharedChannelsOp = createAsyncOp({
    name: 'sync/shared_channels',
    transport: 'http',
    silent: true,
    restMirror: { method: 'GET', path: '/sync/api/v1/company/members/:user_id/shared-channels' },
    request: async ({ payload }) => {
        const { httpRequest } = await import('@platform/lib/events/http.js');
        return httpRequest({
            method: 'GET',
            url: `/sync/api/v1/company/members/${encodeURIComponent(payload.user_id)}/shared-channels`,
        });
    },
});
