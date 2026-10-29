/**
 * Integrations — OAuth credentials для внешних сервисов (Google, GitHub, Telegram).
 * REST: `core/api/integrations.py` — тот же `op_*`, что WS.
 * Authorize и OAuth callback — HTTP (браузерный redirect).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

export const integrationsListOp = createAsyncOp({
    name: 'flows/integrations_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/integrations/credentials_list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/integrations/credentials' },
});

export const integrationsRemoveOp = createAsyncOp({
    name: 'flows/integrations_remove',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/integrations/credentials_remove_requested',
    restMirror: { method: 'DELETE', path: '/flows/api/v1/integrations/credentials/{provider}/{service}' },
    successToastKey: 'flows:toast.integration_removed',
    errorToastKey: 'flows:toast.integration_remove_error',
});

export const googleWorkspaceAuthorizeOp = createAsyncOp({
    name: 'flows/google_workspace_authorize',
    silent: true,
    transport: 'http',
    restMirror: {
        method: 'GET',
        path: '/flows/api/v1/integrations/credentials/google/workspace/authorize',
    },
    request: async ({ payload }) => {
        if (!isPlainRecord(payload)) {
            throw new Error('googleWorkspaceAuthorizeOp: return_path required');
        }
        const returnPath = payload.return_path;
        if (typeof returnPath !== 'string' || returnPath.length === 0) {
            throw new Error('googleWorkspaceAuthorizeOp: return_path required');
        }
        const qs = new URLSearchParams();
        qs.set('return_path', returnPath);
        const returnOrigin = payload.return_origin;
        if (typeof returnOrigin === 'string' && returnOrigin.length > 0) {
            qs.set('return_origin', returnOrigin);
        }
        const data = await httpRequest({
            method: 'GET',
            url: `/flows/api/v1/integrations/credentials/google/workspace/authorize?${qs.toString()}`,
        });
        if (!isPlainRecord(data)) {
            throw new Error('googleWorkspaceAuthorizeOp: authorize_url missing');
        }
        const authorizeUrl = data.authorize_url;
        if (typeof authorizeUrl !== 'string' || authorizeUrl.length === 0) {
            throw new Error('googleWorkspaceAuthorizeOp: authorize_url missing');
        }
        return authorizeUrl;
    },
});

export const googleWorkspaceCompanyGetOp = createAsyncOp({
    name: 'flows/google_workspace_company_get',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/integrations/workspace_company_get_requested',
    restMirror: {
        method: 'GET',
        path: '/flows/api/v1/integrations/credentials/google/workspace/company',
    },
});

export const googleWorkspaceCompanyPutOp = createAsyncOp({
    name: 'flows/google_workspace_company_put',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/integrations/workspace_company_put_requested',
    restMirror: {
        method: 'PUT',
        path: '/flows/api/v1/integrations/credentials/google/workspace/company',
    },
    successToastKey: 'flows:toast.workspace_company_saved',
    errorToastKey: 'flows:toast.workspace_company_save_error',
});

export const googleWorkspaceCompanyDeleteOp = createAsyncOp({
    name: 'flows/google_workspace_company_delete',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/integrations/workspace_company_delete_requested',
    restMirror: {
        method: 'DELETE',
        path: '/flows/api/v1/integrations/credentials/google/workspace/company',
    },
    successToastKey: 'flows:toast.workspace_company_removed',
    errorToastKey: 'flows:toast.workspace_company_remove_error',
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'flows/integrations_list': typeof integrationsListOp;
        'flows/integrations_remove': typeof integrationsRemoveOp;
        'flows/google_workspace_authorize': typeof googleWorkspaceAuthorizeOp;
        'flows/google_workspace_company_get': typeof googleWorkspaceCompanyGetOp;
        'flows/google_workspace_company_put': typeof googleWorkspaceCompanyPutOp;
        'flows/google_workspace_company_delete': typeof googleWorkspaceCompanyDeleteOp;
    }
}
