/**
 * MCP servers — реестр Model Context Protocol серверов.
 * REST: `apps/flows/src/api/v1/mcp.py`.
 */

import { createResourceCollection, createAsyncOp } from '@platform/lib/events/index.js';

export const mcpServersResource = createResourceCollection({
    name: 'flows/mcp_servers',
    baseUrl: '/flows/api/v1/mcp/servers',
    idField: 'server_id',
    operations: ['list', 'get', 'create', 'update', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 15_000,
    listQuery: () => ({ search: '', limit: 200, offset: 0 }),
    restMirror: {
        list: { method: 'GET', path: '/flows/api/v1/mcp/servers' },
        get: { method: 'GET', path: '/flows/api/v1/mcp/servers/:server_id' },
        create: { method: 'POST', path: '/flows/api/v1/mcp/servers' },
        update: { method: 'PUT', path: '/flows/api/v1/mcp/servers/:server_id' },
        remove: { method: 'DELETE', path: '/flows/api/v1/mcp/servers/:server_id' },
    },
    toastKeys: {
        create: 'flows:toast.mcp_server_created',
        create_error: 'flows:toast.mcp_server_create_error',
        update: 'flows:toast.mcp_server_updated',
        update_error: 'flows:toast.mcp_server_update_error',
        remove: 'flows:toast.mcp_server_removed',
        remove_error: 'flows:toast.mcp_server_remove_error',
    },
});

export const mcpServersListOp = createAsyncOp({
    name: 'flows/mcp_servers_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/mcp_servers/list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/mcp/servers' },
});

export const mcpServerSyncOp = createAsyncOp({
    name: 'flows/mcp_server_sync',
    successToastKey: 'flows:toast.mcp_server_synced',
    errorToastKey: 'flows:toast.mcp_server_sync_error',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/mcp_servers/sync_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/mcp/servers/:server_id/sync' },
});

export const mcpServerResetCatalogDefaultsOp = createAsyncOp({
    name: 'flows/mcp_server_reset_catalog_defaults',
    successToastKey: 'flows:toast.mcp_server_reset_catalog_defaults',
    errorToastKey: 'flows:toast.mcp_server_reset_catalog_defaults_error',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/mcp_servers/reset_catalog_defaults_requested',
    restMirror: {
        method: 'POST',
        path: '/flows/api/v1/mcp/servers/:server_id/reset_catalog_defaults',
    },
});

export const mcpServerTestOp = createAsyncOp({
    name: 'flows/mcp_server_test',
    successToastKey: 'flows:toast.mcp_server_tested',
    errorToastKey: 'flows:toast.mcp_server_test_error',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/mcp_servers/test_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/mcp/servers/:server_id/test' },
});

export const mcpBrandingLoadOp = createAsyncOp({
    name: 'flows/mcp_branding_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/mcp_branding/list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/mcp/branding' },
});

export const mcpBrandingSlugSuggestOp = createAsyncOp({
    name: 'flows/mcp_branding_slug_suggest',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/mcp_branding/slug_suggest_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/mcp/branding/slug-suggest' },
});

export const mcpBrandingUpsertOp = createAsyncOp({
    name: 'flows/mcp_branding_upsert',
    successToastKey: 'flows:toast.mcp_branding_saved',
    errorToastKey: 'flows:toast.mcp_branding_save_error',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/mcp_branding/upsert_requested',
    restMirror: { method: 'PUT', path: '/flows/api/v1/mcp/branding/:server_id' },
});

export const mcpBrandingRemoveOp = createAsyncOp({
    name: 'flows/mcp_branding_remove',
    successToastKey: 'flows:toast.mcp_branding_removed',
    errorToastKey: 'flows:toast.mcp_branding_remove_error',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/mcp_branding/remove_requested',
    restMirror: { method: 'DELETE', path: '/flows/api/v1/mcp/branding/:server_id' },
});

export const mcpCatalogStoreLoadOp = createAsyncOp({
    name: 'flows/mcp_catalog_store_load',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/mcp_catalog/list_requested',
    restMirror: { method: 'GET', path: '/flows/api/v1/mcp/catalog' },
});

export const mcpCatalogInstallOp = createAsyncOp({
    name: 'flows/mcp_catalog_install',
    successToastKey: 'flows:toast.mcp_catalog_installed',
    errorToastKey: 'flows:toast.mcp_catalog_install_error',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    commandType: 'flows/mcp_catalog/install_requested',
    restMirror: { method: 'POST', path: '/flows/api/v1/mcp/catalog/:catalog_id/install' },
});

export const mcpCatalogUninstallOp = createAsyncOp({
    name: 'flows/mcp_catalog_uninstall',
    successToastKey: 'flows:toast.mcp_catalog_uninstalled',
    errorToastKey: 'flows:toast.mcp_catalog_uninstall_error',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    commandType: 'flows/mcp_catalog/uninstall_requested',
    restMirror: { method: 'DELETE', path: '/flows/api/v1/mcp/catalog/:catalog_id/install' },
});
