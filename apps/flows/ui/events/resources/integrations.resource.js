/**
 * Integrations — OAuth credentials для внешних сервисов (Google, GitHub, Telegram).
 * REST: core/api/integrations.py (`/flows/api/v1/integrations/credentials`).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const integrationsListOp = createAsyncOp({
    name: 'flows/integrations_list',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/integrations/credentials' },
    request: async () => {
        return httpRequest({ method: 'GET', url: '/flows/api/v1/integrations/credentials' });
    },
});

export const integrationsRemoveOp = createAsyncOp({
    name: 'flows/integrations_remove',
    successToastKey: 'flows:toast.integration_removed',
    errorToastKey: 'flows:toast.integration_remove_error',
    restMirror: { method: 'DELETE', path: '/flows/api/v1/integrations/credentials/{provider}/{service}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.provider !== 'string' || typeof payload.service !== 'string') {
            throw new Error('integrationsRemoveOp: { provider, service } required');
        }
        return httpRequest({
            method: 'DELETE',
            url: `/flows/api/v1/integrations/credentials/${encodeURIComponent(payload.provider)}/${encodeURIComponent(payload.service)}`,
        });
    },
});

export const googleWorkspaceAuthorizeOp = createAsyncOp({
    name: 'flows/google_workspace_authorize',
    silent: true,
    restMirror: {
        method: 'GET',
        path: '/flows/api/v1/integrations/credentials/google/workspace/authorize',
    },
    request: async ({ payload }) => {
        const returnPath = typeof payload?.return_path === 'string' ? payload.return_path : '/';
        const qs = new URLSearchParams();
        qs.set('return_path', returnPath);
        if (typeof payload?.return_origin === 'string' && payload.return_origin.length > 0) {
            qs.set('return_origin', payload.return_origin);
        }
        const data = await httpRequest({
            method: 'GET',
            url: `/flows/api/v1/integrations/credentials/google/workspace/authorize?${qs.toString()}`,
        });
        if (!data || typeof data.authorize_url !== 'string' || data.authorize_url.length === 0) {
            throw new Error('googleWorkspaceAuthorizeOp: authorize_url missing');
        }
        return data.authorize_url;
    },
});

export const googleWorkspaceCompanyGetOp = createAsyncOp({
    name: 'flows/google_workspace_company_get',
    silent: true,
    restMirror: {
        method: 'GET',
        path: '/flows/api/v1/integrations/credentials/google/workspace/company',
    },
    request: async () => {
        return httpRequest({
            method: 'GET',
            url: '/flows/api/v1/integrations/credentials/google/workspace/company',
        });
    },
});

export const googleWorkspaceCompanyPutOp = createAsyncOp({
    name: 'flows/google_workspace_company_put',
    successToastKey: 'flows:toast.workspace_company_saved',
    errorToastKey: 'flows:toast.workspace_company_save_error',
    restMirror: {
        method: 'PUT',
        path: '/flows/api/v1/integrations/credentials/google/workspace/company',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.service_account_json !== 'string') {
            throw new Error('googleWorkspaceCompanyPutOp: service_account_json required');
        }
        const body = {
            service_account_json: payload.service_account_json,
            impersonate_email:
                typeof payload.impersonate_email === 'string' && payload.impersonate_email.trim().length > 0
                    ? payload.impersonate_email.trim()
                    : null,
        };
        return httpRequest({
            method: 'PUT',
            url: '/flows/api/v1/integrations/credentials/google/workspace/company',
            body,
        });
    },
});

export const googleWorkspaceCompanyDeleteOp = createAsyncOp({
    name: 'flows/google_workspace_company_delete',
    successToastKey: 'flows:toast.workspace_company_removed',
    errorToastKey: 'flows:toast.workspace_company_remove_error',
    restMirror: {
        method: 'DELETE',
        path: '/flows/api/v1/integrations/credentials/google/workspace/company',
    },
    request: async () => {
        return httpRequest({
            method: 'DELETE',
            url: '/flows/api/v1/integrations/credentials/google/workspace/company',
        });
    },
});
