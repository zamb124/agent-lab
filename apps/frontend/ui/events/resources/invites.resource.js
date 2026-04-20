/**
 * Invites resource — приём инвайта по короткой ссылке.
 *
 * API: POST /frontend/api/invites/accept { short_code }
 *      → { company_id, company_name, role, already_member }
 *
 * onSuccess: перевыпуск сессионного cookie выполнен на бэке (active_company_id
 * указывает на новую компанию). Перезагружаем текущего пользователя через
 * core auth-effect и переходим на dashboard.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { CoreAuthEvents } from '@platform/lib/events/effects/auth.effect.js';

export const acceptInviteOp = createAsyncOp({
    name: 'frontend/invite_accept',
    successToastKey: 'frontend:join_page.toast_accepted',
    errorToastKey: 'frontend:join_page.toast_failed',
    restMirror: { method: 'POST', path: '/frontend/api/invites/accept' },
    request: async ({ payload }) => {
        const shortCode = payload && payload.short_code;
        if (!shortCode) throw new Error('invite_accept: short_code required');
        return await httpRequest({
            method: 'POST',
            url: '/frontend/api/invites/accept',
            body: { short_code: shortCode },
        });
    },
    onSuccess: (ctx) => {
        ctx.dispatch(CoreAuthEvents.USER_LOAD_REQUESTED, null, { source: 'local' });
        ctx.dispatch(
            CoreEvents.ROUTER_NAVIGATE_REQUESTED,
            { routeKey: 'dashboard' },
            { source: 'local' },
        );
    },
});
