/**
 * Team resources — участники компании и генерация invite-ссылок.
 *
 * Coverage:
 *   - teamMembersResource (createResourceCollection): список участников,
 *     обновление ролей, удаление участника. Создание участника отсутствует —
 *     приглашения идут через `inviteGenerateOp`.
 *   - inviteGenerateOp (createAsyncOp): генерация одноразовой invite-ссылки.
 *     Сгенерированные ссылки хранятся в slice как `links: { [role]: link }`,
 *     чтобы UI мог показать конкретную ссылку для выбранной роли без
 *     собственного локального состояния.
 *
 * Backend:
 *   GET    /frontend/api/team/members           → { items: TeamMember[] }
 *   PATCH  /frontend/api/team/members/{user_id} → { success, user_id, roles }
 *   DELETE /frontend/api/team/members/{user_id} → { success, message }
 *   POST   /frontend/api/invites/generate       → { invite_url, role, ... }
 */

import {
    createResourceCollection,
    createAsyncOp,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const teamMembersResource = createResourceCollection({
    name: 'frontend/team_members',
    baseUrl: '/frontend/api/team/members',
    idField: 'user_id',
    operations: ['list', 'update', 'remove'],
    toastKeys: {
        update: 'frontend:team_page.toast_role_updated',
        remove: 'frontend:team_page.toast_member_removed',
    },
});

export const inviteGenerateOp = createAsyncOp({
    name: 'frontend/team_invite',
    successToastKey: 'frontend:team_page.toast_invite_generated',
    errorToastKey: 'frontend:team_page.err_invite',
    restMirror: { method: 'POST', path: '/frontend/api/invites/generate' },
    request: async ({ payload }) => {
        const role = payload && payload.role;
        if (!role) throw new Error('inviteGenerateOp: role required');
        const response = await httpRequest({
            method: 'POST',
            url: '/frontend/api/invites/generate',
            body: { role },
        });
        let link = '';
        if (typeof response.invite_url === 'string' && response.invite_url.length > 0) link = response.invite_url;
        else if (typeof response.link === 'string' && response.link.length > 0) link = response.link;
        else if (typeof response.url === 'string' && response.url.length > 0) link = response.url;
        if (!link) throw new Error('inviteGenerateOp: server did not return invite link');
        return { role, link };
    },
    extraInitial: { links: {} },
    extraReducer: (state, event, events) => {
        if (event.type === events.SUCCEEDED) {
            const result = event.payload && event.payload.result;
            if (result && result.role && result.link) {
                return { ...state, links: { ...state.links, [result.role]: result.link } };
            }
        }
        return state;
    },
});
