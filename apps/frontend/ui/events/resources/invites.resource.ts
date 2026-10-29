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
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { buildCompanySubdomainUrl } from '@platform/lib/utils/company-url.js';

function shortCodeOf(payload: unknown, label: string): string {
    if (!isPlainRecord(payload)) {
        throw new Error(`${label}: short_code required`);
    }
    const shortCode = payload.short_code;
    if (typeof shortCode !== 'string' || shortCode === '') {
        throw new Error(`${label}: short_code required`);
    }
    return shortCode;
}

function acceptedSubdomain(result: unknown): string {
    if (!isPlainRecord(result)) {
        throw new Error('invite_accept: subdomain required in result');
    }
    const subdomain = result.subdomain;
    if (typeof subdomain !== 'string' || subdomain.trim() === '') {
        throw new Error('invite_accept: subdomain required in result');
    }
    return subdomain.trim();
}

export const previewInviteOp = createAsyncOp({
    name: 'frontend/invite_preview',
    silent: true,
    restMirror: { method: 'POST', path: '/frontend/api/invites/preview' },
    request: async ({ payload }) => {
        const shortCode = shortCodeOf(payload, 'invite_preview');
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
        const shortCode = shortCodeOf(payload, 'invite_accept');
        return await httpRequest({
            method: 'POST',
            url: '/frontend/api/invites/accept',
            body: { short_code: shortCode },
        });
    },
    onSuccess: (_ctx, result) => {
        const subdomain = acceptedSubdomain(result);
        const path = '/dashboard';
        window.location.replace(buildCompanySubdomainUrl(subdomain, path));
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'frontend/invite_preview': typeof previewInviteOp;
        'frontend/invite_accept': typeof acceptInviteOp;
    }
}
