/**
 * Участники компании Sync — список участников компании для DM-секции и поиска.
 *
 * `transport: 'ws'` — единый канал для READ-операций. REST-зеркала живут в
 * `apps/sync/api/company.py`.
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
    transport: 'ws',
    wsTimeoutMs: 5_000,
    mapItem: _normalizeMember,
});

export const sharedChannelsOp = createAsyncOp({
    name: 'sync/shared_channels',
    transport: 'ws',
    wsTimeoutMs: 5_000,
    silent: true,
    commandType: 'sync/shared_channels/list_requested',
    restMirror: { method: 'GET', path: '/sync/api/v1/company/members/:peer_user_id/shared-channels' },
});
