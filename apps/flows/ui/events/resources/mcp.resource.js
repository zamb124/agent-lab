/**
 * MCP servers — реестр Model Context Protocol серверов.
 * REST: `apps/flows/src/api/v1/mcp.py`.
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const mcpServersResource = createResourceCollection({
    name: 'flows/mcp_servers',
    baseUrl: '/flows/api/v1/mcp/servers',
    idField: 'server_id',
    operations: ['list', 'get', 'create', 'remove'],
    toastKeys: {
        create: 'flows:toast.mcp_server_created',
        create_error: 'flows:toast.mcp_server_create_error',
        remove: 'flows:toast.mcp_server_removed',
        remove_error: 'flows:toast.mcp_server_remove_error',
    },
});

// Бэкенд требует PUT (а не PATCH).
export const mcpServerUpdateOp = createAsyncOp({
    name: 'flows/mcp_server_update',
    successToastKey: 'flows:toast.mcp_server_updated',
    errorToastKey: 'flows:toast.mcp_server_update_error',
    restMirror: { method: 'PUT', path: '/flows/api/v1/mcp/servers/{server_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.server_id !== 'string' || !payload.body) {
            throw new Error('mcpServerUpdateOp: { server_id, body } required');
        }
        return httpRequest({
            method: 'PUT',
            url: `/flows/api/v1/mcp/servers/${encodeURIComponent(payload.server_id)}`,
            body: payload.body,
        });
    },
});

export const mcpServerSyncOp = createAsyncOp({
    name: 'flows/mcp_server_sync',
    successToastKey: 'flows:toast.mcp_server_synced',
    errorToastKey: 'flows:toast.mcp_server_sync_error',
    restMirror: { method: 'POST', path: '/flows/api/v1/mcp/servers/{server_id}/sync' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.server_id !== 'string' || payload.server_id.length === 0) {
            throw new Error('mcpServerSyncOp: { server_id } required');
        }
        return httpRequest({
            method: 'POST',
            url: `/flows/api/v1/mcp/servers/${encodeURIComponent(payload.server_id)}/sync`,
            body: {},
        });
    },
});

export const mcpServerResetCatalogDefaultsOp = createAsyncOp({
    name: 'flows/mcp_server_reset_catalog_defaults',
    successToastKey: 'flows:toast.mcp_server_reset_catalog_defaults',
    errorToastKey: 'flows:toast.mcp_server_reset_catalog_defaults_error',
    restMirror: {
        method: 'POST',
        path: '/flows/api/v1/mcp/servers/{server_id}/reset_catalog_defaults',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.server_id !== 'string' || payload.server_id.length === 0) {
            throw new Error('mcpServerResetCatalogDefaultsOp: { server_id } required');
        }
        return httpRequest({
            method: 'POST',
            url: `/flows/api/v1/mcp/servers/${encodeURIComponent(payload.server_id)}/reset_catalog_defaults`,
            body: {},
        });
    },
});

export const mcpServerTestOp = createAsyncOp({
    name: 'flows/mcp_server_test',
    successToastKey: 'flows:toast.mcp_server_tested',
    errorToastKey: 'flows:toast.mcp_server_test_error',
    restMirror: { method: 'POST', path: '/flows/api/v1/mcp/servers/{server_id}/test' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.server_id !== 'string' || payload.server_id.length === 0) {
            throw new Error('mcpServerTestOp: { server_id } required');
        }
        return httpRequest({
            method: 'POST',
            url: `/flows/api/v1/mcp/servers/${encodeURIComponent(payload.server_id)}/test`,
            body: {},
        });
    },
});

export const mcpBrandingLoadOp = createAsyncOp({
    name: 'flows/mcp_branding_load',
    silent: true,
    restMirror: { method: 'GET', path: '/flows/api/v1/mcp/branding' },
    request: async () => httpRequest({
        method: 'GET',
        url: '/flows/api/v1/mcp/branding',
    }),
});

export const mcpBrandingUpsertOp = createAsyncOp({
    name: 'flows/mcp_branding_upsert',
    successToastKey: 'flows:toast.mcp_branding_saved',
    errorToastKey: 'flows:toast.mcp_branding_save_error',
    restMirror: { method: 'PUT', path: '/flows/api/v1/mcp/branding/{server_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.server_id !== 'string' || payload.server_id.length === 0) {
            throw new Error('mcpBrandingUpsertOp: { server_id, icon_file_id } required');
        }
        if (typeof payload.icon_file_id !== 'string' || payload.icon_file_id.length === 0) {
            throw new Error('mcpBrandingUpsertOp: icon_file_id required');
        }
        return httpRequest({
            method: 'PUT',
            url: `/flows/api/v1/mcp/branding/${encodeURIComponent(payload.server_id)}`,
            body: { icon_file_id: payload.icon_file_id },
        });
    },
});

export const mcpBrandingRemoveOp = createAsyncOp({
    name: 'flows/mcp_branding_remove',
    successToastKey: 'flows:toast.mcp_branding_removed',
    errorToastKey: 'flows:toast.mcp_branding_remove_error',
    restMirror: { method: 'DELETE', path: '/flows/api/v1/mcp/branding/{server_id}' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.server_id !== 'string' || payload.server_id.length === 0) {
            throw new Error('mcpBrandingRemoveOp: { server_id } required');
        }
        return httpRequest({
            method: 'DELETE',
            url: `/flows/api/v1/mcp/branding/${encodeURIComponent(payload.server_id)}`,
        });
    },
});
