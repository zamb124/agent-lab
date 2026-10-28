/**
 * Ресурсы команды — участники компании и генерация invite-ссылок
 * (команды `frontend/team/*`, `frontend/invites/generate_requested`;
 * REST-зеркало `apps/frontend/api/team.py`, `invites.py`).
 *
 * Coverage:
 *   - teamMembersResource (createResourceCollection): список участников,
 *     обновление ролей, удаление участника. Создание участника отсутствует —
 *     приглашения идут через `inviteGenerateOp`.
 *   - inviteGenerateOp (createAsyncOp, silent): генерация invite-ссылки;
 *     slice `links: { [role]: invite_url }` кэширует ссылку для повторного копирования.
 */

import {
    createResourceCollection,
    createAsyncOp,
} from '@platform/lib/events/index.js';

export const teamMembersResource = createResourceCollection({
    name: 'frontend/team',
    baseUrl: '/frontend/api/team/members',
    idField: 'user_id',
    operations: ['list', 'update', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({ limit: 200, offset: 0 }),
    toastKeys: {
        update: 'frontend:team_page.toast_role_updated',
        remove: 'frontend:team_page.toast_member_removed',
    },
});

export const inviteGenerateOp = createAsyncOp({
    name: 'frontend/team_invite',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'frontend/invites/generate_requested',
    restMirror: { method: 'POST', path: '/frontend/api/invites/generate' },
    extraInitial: { links: {} },
    extraReducer: (state, event, events) => {
        if (event.type === events.SUCCEEDED) {
            const result = (event.payload as Record<string, any>) && (event.payload as Record<string, any>).result;
            if (!result || typeof result.role !== 'string' || typeof result.invite_url !== 'string') {
                throw new Error('inviteGenerateOp: result.role and result.invite_url required');
            }
            return { ...state, links: { ...(state.links as Record<string, unknown>), [(result as Record<string, any>).role]: (result as Record<string, any>).invite_url } };
        }
        return state;
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'frontend/team': typeof teamMembersResource;
        'frontend/team_invite': typeof inviteGenerateOp;
    }
}
