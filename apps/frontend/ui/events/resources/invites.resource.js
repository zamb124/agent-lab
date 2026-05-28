/**
 * Ресурс инвайтов — приём инвайта по короткой ссылке.
 *
 * API: POST /frontend/api/invites/accept { short_code }
 *      → { company_id, company_name, role, already_member, subdomain }
 *
 * onSuccess: cookie перевыпущен на бэке; полная перезагрузка на dashboard субдомена
 * приглашённой компании (согласовано с JWT и Host-тенантом).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { buildCompanySubdomainUrl } from '@platform/lib/utils/company-url.js';
import { INVITE_DASHBOARD_QUERY } from '@platform/lib/utils/last-visited-service.js';

export const previewInviteOp = createAsyncOp({
    name: 'frontend/invite_preview',
    silent: true,
    restMirror: { method: 'POST', path: '/frontend/api/invites/preview' },
    request: async ({ payload }) => {
        const shortCode = payload && payload.short_code;
        if (!shortCode) throw new Error('invite_preview: short_code required');
        return await httpRequest({
            method: 'POST',
            url: '/frontend/api/invites/preview',
            body: { short_code: shortCode },
        });
    },
});

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
    onSuccess: (_ctx, result) => {
        if (!result || typeof result.subdomain !== 'string' || result.subdomain.trim() === '') {
            throw new Error('invite_accept: subdomain required in result');
        }
        const path = `/dashboard?${INVITE_DASHBOARD_QUERY}=1`;
        window.location.replace(buildCompanySubdomainUrl(result.subdomain.trim(), path));
    },
});
